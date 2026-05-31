import asyncio
import json

from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import connect as ws_connect

from app.config import Settings
from app.schemas.jobs import SupportJob
from app.services.orchestrator import SupportOrchestrator
from app.services.prod.client import BackendClient
from app.services.reply.builder import build_job_result
from app.services.runtime.hub import AgentHub
from app.utils.logger import get_logger

logger = get_logger(__name__)


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: SupportOrchestrator,
        prod_client: BackendClient,
        hub: AgentHub,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self.prod_client = prod_client
        self.hub = hub
        self._task: asyncio.Task | None = None
        self._running = False
        self._active_runtime_task_id: str | None = None
        self._active_job: SupportJob | None = None

    async def start(self) -> None:
        if not self.settings.WORKER_ENABLED:
            logger.info("Worker disabled by config")
            return

        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Worker started in websocket mode")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        reconnect_delay = self.settings.WORKER_RECONNECT_DELAY_SECONDS

        while self._running:
            try:
                ws_url = self.prod_client.worker_ws_url()
                headers = self.prod_client.ws_headers()

                if not ws_url:
                    logger.warning("Worker websocket url is empty")
                    await asyncio.sleep(reconnect_delay)
                    continue

                async with ws_connect(
                    ws_url,
                    extra_headers=headers,
                    open_timeout=20,
                    ping_interval=self.settings.WORKER_WS_PING_INTERVAL_SECONDS,
                    ping_timeout=self.settings.WORKER_WS_PING_TIMEOUT_SECONDS,
                    close_timeout=10,
                    max_size=8_000_000,
                ) as websocket:
                    logger.info("Worker websocket connected to %s", ws_url)
                    reconnect_delay = self.settings.WORKER_RECONNECT_DELAY_SECONDS

                    await websocket.send(
                        json.dumps(
                            {
                                "type": "worker.hello",
                                "worker_name": self.settings.WORKER_NAME,
                            }
                        )
                    )

                    while self._running:
                        raw = await websocket.recv()
                        payload = json.loads(raw)

                        if not isinstance(payload, dict):
                            continue

                        msg_type = str(payload.get("type") or "").strip()

                        if msg_type == "worker.registered":
                            logger.info(
                                "Worker registered as %s", payload.get("worker_name")
                            )
                            continue

                        if msg_type == "worker.pong":
                            continue

                        if msg_type != "job.assign":
                            logger.debug(
                                "Unknown worker websocket message: %s", payload
                            )
                            continue

                        await self._handle_assigned_job(websocket, payload)

            except asyncio.CancelledError:
                break
            except ConnectionClosed as exc:
                logger.warning(
                    "Worker websocket closed: code=%s reason=%s", exc.code, exc.reason
                )
                await self._report_transport_drop()
            except Exception as exc:
                logger.exception("Worker websocket loop failed: %s", exc)
                await self._report_transport_drop()

            if not self._running:
                break

            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(
                reconnect_delay * 2,
                self.settings.WORKER_MAX_RECONNECT_DELAY_SECONDS,
            )

    async def _handle_assigned_job(self, websocket, payload: dict) -> None:
        job = self._parse_job(payload)
        runtime_task_id = await self.hub.begin_worker_job(job)

        self._active_job = job
        self._active_runtime_task_id = runtime_task_id

        async def emit_stage(
            stage: str, message: str, meta: dict | None = None
        ) -> None:
            await self.hub.worker_stage(runtime_task_id, stage, message, meta)

        try:
            reply = await self.orchestrator.process_job(job, stage_cb=emit_stage)
        except Exception as exc:
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "job.fail",
                            "job_id": job.job_id,
                            "error": str(exc),
                        }
                    )
                )
            except Exception:
                logger.exception("Failed to send job.fail for job_id=%s", job.job_id)
                raise

            await self.hub.fail_worker_job(runtime_task_id, job, exc)
            self._active_job = None
            self._active_runtime_task_id = None
            return

        result_payload = build_job_result(job.job_id, reply).model_dump()

        try:
            await websocket.send(
                json.dumps(
                    {
                        "type": "job.complete",
                        "job_id": job.job_id,
                        "payload": result_payload,
                    }
                )
            )
        except Exception:
            logger.exception("Failed to send job.complete for job_id=%s", job.job_id)
            raise

        await self.hub.complete_worker_job(runtime_task_id, job, reply)
        self._active_job = None
        self._active_runtime_task_id = None

    async def _report_transport_drop(self) -> None:
        if self._active_job is None or self._active_runtime_task_id is None:
            return

        job = self._active_job
        runtime_task_id = self._active_runtime_task_id

        self._active_job = None
        self._active_runtime_task_id = None

        await self.hub.fail_worker_job(
            runtime_task_id,
            job,
            RuntimeError("worker_socket_disconnected_before_ack"),
        )

    def _parse_job(self, payload: dict) -> SupportJob:
        raw_job = payload.get("job") or {}
        raw_payload = raw_job.get("payload") or {}

        if not isinstance(raw_payload, dict):
            raise ValueError("job payload must be an object")

        raw_payload = {
            "job_id": raw_job.get("job_id"),
            **raw_payload,
        }

        return SupportJob.model_validate(raw_payload)

