from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.schemas.jobs import SupportJob
from app.schemas.replies import AgentReply
from app.services.orchestrator import SupportOrchestrator
from app.utils.logger import get_logger

logger = get_logger(__name__)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentHub:
    def __init__(self, *, orchestrator: SupportOrchestrator) -> None:
        self.orchestrator = orchestrator

        self.clients: set[WebSocket] = set()
        self.tasks: dict[str, dict[str, Any]] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=500)
        self.logs: deque[dict[str, Any]] = deque(maxlen=1000)
        self.queue: deque[str] = deque()

        self.completed_today = 0
        self.failed_today = 0
        self.messages_sent_today = 0
        self.last_error = ""
        self.last_answer_preview = ""
        self.last_reply_at: str | None = None

        self.status = "offline"
        self.current_stage = "idle"
        self.current_task_id: str | None = None
        self.current_task_title: str | None = None
        self.last_heartbeat: str | None = None
        self.last_event_at: str | None = None

        self.paused = False
        self._running = False
        self._runner_task: asyncio.Task | None = None
        self._current_process_task: asyncio.Task | None = None
        self._condition = asyncio.Condition()

        self.recent_conversations: deque[dict[str, Any]] = deque(maxlen=100)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.status = "idle"
        self.current_stage = "idle"
        self.last_heartbeat = utc_iso()
        self.last_event_at = self.last_heartbeat
        self._runner_task = asyncio.create_task(
            self._runner(), name="support-agent-runtime-runner"
        )
        self._append_log(
            level="info",
            source="runtime",
            message="Support runtime started",
        )

    async def stop(self) -> None:
        self._running = False
        self.status = "offline"
        self.current_stage = "offline"

        async with self._condition:
            self._condition.notify_all()

        if self._current_process_task:
            self._current_process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._current_process_task

        if self._runner_task:
            self._runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_task

        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})

    async def _safe_send(self, websocket: WebSocket, payload: dict[str, Any]) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError):
            self.disconnect(websocket)
            return False
        except Exception:
            self.disconnect(websocket)
            logger.debug("WebSocket send failed during support hub send", exc_info=True)
            return False

    async def connect(self, websocket: WebSocket) -> bool:
        try:
            await websocket.accept()
        except Exception:
            logger.debug("WebSocket accept failed", exc_info=True)
            return False

        self.clients.add(websocket)
        self.last_heartbeat = utc_iso()

        initial_payloads = [
            {"type": "agent.state", "state": self.state_snapshot()},
            {"type": "agent.queue", "items": self.queue_snapshot()},
            {"type": "agent.history", "items": self.history_snapshot()},
            {"type": "agent.logs", "items": list(self.logs)[-200:]},
            {"type": "agent.conversations", "items": self.conversations_snapshot()},
            {"type": "agent.connected", "ok": True},
        ]

        for payload in initial_payloads:
            ok = await self._safe_send(websocket, payload)
            if not ok:
                return False

        return True

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def handle_command(
        self, payload: dict[str, Any], websocket: WebSocket | None = None
    ) -> None:
        msg_type = str(payload.get("type") or "").strip()

        if msg_type == "agent.connect":
            if websocket is not None:
                await self._safe_send(
                    websocket, {"type": "agent.state", "state": self.state_snapshot()}
                )
                await self._safe_send(
                    websocket, {"type": "agent.queue", "items": self.queue_snapshot()}
                )
                await self._safe_send(
                    websocket,
                    {"type": "agent.history", "items": self.history_snapshot()},
                )
                await self._safe_send(
                    websocket, {"type": "agent.logs", "items": list(self.logs)[-200:]}
                )
                await self._safe_send(
                    websocket,
                    {
                        "type": "agent.conversations",
                        "items": self.conversations_snapshot(),
                    },
                )
            return

        if msg_type == "agent.requestState":
            if websocket is not None:
                await self._safe_send(
                    websocket, {"type": "agent.state", "state": self.state_snapshot()}
                )
            return

        if msg_type == "agent.requestQueue":
            if websocket is not None:
                await self._safe_send(
                    websocket, {"type": "agent.queue", "items": self.queue_snapshot()}
                )
            return

        if msg_type == "agent.requestHistory":
            if websocket is not None:
                await self._safe_send(
                    websocket,
                    {"type": "agent.history", "items": self.history_snapshot()},
                )
            return

        if msg_type == "agent.pause":
            self.paused = True
            self.status = "paused"
            self.current_stage = "paused"
            self._append_log(
                level="warning", source="runtime", message="Agent paused from UI"
            )
            await self.broadcast(
                {"type": "agent.state", "state": self.state_snapshot()}
            )
            return

        if msg_type == "agent.resume":
            self.paused = False
            if self.current_task_id:
                self.status = "running"
            else:
                self.status = "idle"
                self.current_stage = "idle"
            self._append_log(
                level="info", source="runtime", message="Agent resumed from UI"
            )
            async with self._condition:
                self._condition.notify_all()
            await self.broadcast(
                {"type": "agent.state", "state": self.state_snapshot()}
            )
            return

        if msg_type == "agent.clearHistory":
            self.history.clear()
            self.recent_conversations.clear()
            self._append_log(
                level="info", source="runtime", message="History cleared from UI"
            )
            await self.broadcast(
                {"type": "agent.history", "items": self.history_snapshot()}
            )
            await self.broadcast(
                {"type": "agent.conversations", "items": self.conversations_snapshot()}
            )
            return

        if msg_type == "agent.clearLogs":
            self.logs.clear()
            self._append_log(
                level="info", source="runtime", message="Logs cleared from UI"
            )
            await self.broadcast(
                {"type": "agent.logs", "items": list(self.logs)[-200:]}
            )
            return

        if msg_type == "task.create":
            prompt = str(payload.get("prompt") or "").strip()
            title = str(payload.get("title") or "").strip() or "Manual task"
            if not prompt:
                if websocket is not None:
                    await self._safe_send(
                        websocket,
                        {
                            "type": "agent.error",
                            "message": "Prompt is empty",
                        },
                    )
                return
            await self.enqueue_task(
                title=title,
                prompt=prompt,
                source="office-ui",
            )
            return

        if msg_type == "task.cancel":
            task_id = str(payload.get("taskId") or "").strip()
            if task_id:
                await self.cancel_task(task_id)
            return

        if msg_type == "task.retry":
            task_id = str(payload.get("taskId") or "").strip()
            if task_id:
                await self.retry_task(task_id)
            return

    async def enqueue_task(
        self, *, title: str, prompt: str, source: str
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:12]
        now = utc_iso()
        task = {
            "id": task_id,
            "title": title,
            "prompt": prompt,
            "source": source,
            "status": "queued",
            "stage": "queued",
            "createdAt": now,
            "startedAt": None,
            "finishedAt": None,
            "error": "",
            "answer": "",
            "answerPreview": "",
            "intent": "",
            "confidence": 0.0,
            "needsHandoff": False,
            "handoffReason": "",
            "tags": [],
            "usedChunkIds": [],
            "cancelRequested": False,
            "userKey": "office:support",
            "ticketId": f"office:{title}",
            "threadId": 0,
            "contactLabel": "Office task",
            "channel": "office",
            "lastReplyAt": None,
        }
        self.tasks[task_id] = task
        self.queue.append(task_id)

        self._append_log(
            level="info",
            source="queue",
            message=f"Task queued: {title}",
            task_id=task_id,
            stage="queued",
        )

        await self.broadcast({"type": "task.accepted", "task": self.task_public(task)})
        await self.broadcast({"type": "agent.queue", "items": self.queue_snapshot()})
        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})

        async with self._condition:
            self._condition.notify_all()

        return task

    async def cancel_task(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        if task["status"] == "queued":
            try:
                self.queue.remove(task_id)
            except ValueError:
                pass
            task["status"] = "cancelled"
            task["stage"] = "cancelled"
            task["finishedAt"] = utc_iso()

            self._append_log(
                level="warning",
                source="queue",
                message=f"Queued task cancelled: {task['title']}",
                task_id=task_id,
                stage="cancelled",
            )

            self.history.appendleft(self.task_public(task))
            await self.broadcast(
                {"type": "task.cancelled", "task": self.task_public(task)}
            )
            await self.broadcast(
                {"type": "agent.queue", "items": self.queue_snapshot()}
            )
            await self.broadcast(
                {"type": "agent.history", "items": self.history_snapshot()}
            )
            await self.broadcast(
                {"type": "agent.state", "state": self.state_snapshot()}
            )
            return

        if (
            task["status"] == "running"
            and self.current_task_id == task_id
            and self._current_process_task
        ):
            task["cancelRequested"] = True
            self._current_process_task.cancel()
            return

    async def retry_task(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        await self.enqueue_task(
            title=f"{task['title']} (retry)",
            prompt=task["prompt"],
            source="office-ui-retry",
        )

    async def begin_worker_job(self, job: SupportJob) -> str:
        task_id = f"job:{job.job_id}"
        now = utc_iso()
        contact_label = self._contact_label(job)

        task = self.tasks.get(task_id)
        if task is None:
            task = {
                "id": task_id,
                "title": f"{contact_label}",
                "prompt": job.message.text,
                "source": "prod-worker",
                "status": "running",
                "stage": "preparing",
                "createdAt": now,
                "startedAt": now,
                "finishedAt": None,
                "error": "",
                "answer": "",
                "answerPreview": "",
                "intent": "",
                "confidence": 0.0,
                "needsHandoff": False,
                "handoffReason": "",
                "tags": [],
                "usedChunkIds": [],
                "cancelRequested": False,
                "userKey": job.user_key,
                "ticketId": job.ticket_id,
                "threadId": job.thread_id,
                "contactLabel": contact_label,
                "channel": job.meta.channel or "",
                "lastReplyAt": None,
            }
            self.tasks[task_id] = task
        else:
            task.update(
                {
                    "title": f"{contact_label}",
                    "prompt": job.message.text,
                    "status": "running",
                    "stage": "preparing",
                    "startedAt": now,
                    "finishedAt": None,
                    "error": "",
                    "userKey": job.user_key,
                    "ticketId": job.ticket_id,
                    "threadId": job.thread_id,
                    "contactLabel": contact_label,
                    "channel": job.meta.channel or "",
                }
            )

        self.status = "running"
        self.current_stage = "preparing"
        self.current_task_id = task_id
        self.current_task_title = task["title"]
        self.last_event_at = now
        self.last_heartbeat = now
        self.last_error = ""

        self._append_log(
            level="info",
            source="worker",
            message=f"Job started for {contact_label}",
            task_id=task_id,
            stage="preparing",
            meta={
                "ticketId": job.ticket_id,
                "threadId": job.thread_id,
                "channel": job.meta.channel,
                "userKey": job.user_key,
            },
        )

        await self.broadcast({"type": "task.started", "task": self.task_public(task)})
        await self.broadcast({"type": "agent.queue", "items": self.queue_snapshot()})
        await self.broadcast({"type": "agent.logs", "items": list(self.logs)[-200:]})
        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})
        return task_id

    async def worker_stage(
        self,
        task_id: str,
        stage: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        task["stage"] = stage
        self.current_stage = stage
        self.last_event_at = utc_iso()
        self.last_heartbeat = self.last_event_at

        entry = {
            "timestamp": self.last_event_at,
            "level": "info",
            "source": "worker",
            "taskId": task_id,
            "stage": stage,
            "message": message,
            "meta": meta or {},
        }
        self.logs.append(entry)

        await self.broadcast(
            {
                "type": "task.stage",
                "taskId": task_id,
                "stage": stage,
                "message": message,
                "meta": meta or {},
            }
        )
        await self.broadcast({"type": "agent.logs", "items": list(self.logs)[-200:]})
        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})

    async def complete_worker_job(
        self, task_id: str, job: SupportJob, reply: AgentReply
    ) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        finished_at = utc_iso()
        task["status"] = "completed"
        task["stage"] = "completed"
        task["finishedAt"] = finished_at
        task["answer"] = reply.answer
        task["answerPreview"] = (reply.answer or "")[:240]
        task["intent"] = reply.intent
        task["confidence"] = reply.confidence
        task["needsHandoff"] = reply.needs_handoff
        task["handoffReason"] = reply.handoff_reason
        task["tags"] = list(reply.tags)
        task["usedChunkIds"] = list(reply.used_chunk_ids)
        task["lastReplyAt"] = finished_at

        self.completed_today += 1
        self.messages_sent_today += 1
        self.last_answer_preview = task["answerPreview"]
        self.last_reply_at = finished_at
        self.last_event_at = finished_at
        self.last_heartbeat = finished_at

        self._touch_conversation(job=job, reply=reply, reply_at=finished_at)

        self._append_log(
            level="info",
            source="worker",
            message=f"Reply sent to {task['contactLabel']}",
            task_id=task_id,
            stage="completed",
            meta={
                "ticketId": job.ticket_id,
                "threadId": job.thread_id,
                "userKey": job.user_key,
                "channel": job.meta.channel,
            },
        )

        self.history.appendleft(self.task_public(task))

        await self.broadcast({"type": "task.completed", "task": self.task_public(task)})
        await self.broadcast(
            {
                "type": "task.output",
                "taskId": task_id,
                "output": {
                    "answer": reply.answer,
                    "intent": reply.intent,
                    "confidence": reply.confidence,
                    "needsHandoff": reply.needs_handoff,
                    "handoffReason": reply.handoff_reason,
                    "tags": reply.tags,
                    "usedChunkIds": reply.used_chunk_ids,
                },
            }
        )
        await self.broadcast(
            {"type": "agent.history", "items": self.history_snapshot()}
        )
        await self.broadcast({"type": "agent.logs", "items": list(self.logs)[-200:]})
        await self.broadcast(
            {"type": "agent.conversations", "items": self.conversations_snapshot()}
        )

        self.current_task_id = None
        self.current_task_title = None
        self.status = "paused" if self.paused else "idle"
        self.current_stage = "paused" if self.paused else "idle"

        await self.broadcast({"type": "agent.queue", "items": self.queue_snapshot()})
        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})

    async def fail_worker_job(
        self, task_id: str, job: SupportJob, exc: Exception
    ) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        finished_at = utc_iso()
        task["status"] = "failed"
        task["stage"] = "failed"
        task["finishedAt"] = finished_at
        task["error"] = str(exc)

        self.failed_today += 1
        self.last_error = str(exc)
        self.last_event_at = finished_at
        self.last_heartbeat = finished_at

        self._append_log(
            level="error",
            source="worker",
            message=f"Job failed for {task['contactLabel']}: {exc}",
            task_id=task_id,
            stage="failed",
            meta={
                "ticketId": job.ticket_id,
                "threadId": job.thread_id,
                "userKey": job.user_key,
                "channel": job.meta.channel,
            },
        )

        self.history.appendleft(self.task_public(task))

        await self.broadcast({"type": "task.failed", "task": self.task_public(task)})
        await self.broadcast(
            {"type": "agent.history", "items": self.history_snapshot()}
        )
        await self.broadcast({"type": "agent.logs", "items": list(self.logs)[-200:]})

        self.current_task_id = None
        self.current_task_title = None
        self.status = "paused" if self.paused else "idle"
        self.current_stage = "paused" if self.paused else "idle"

        await self.broadcast({"type": "agent.queue", "items": self.queue_snapshot()})
        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})

    def _contact_label(self, job: SupportJob) -> str:
        user_key = (job.user_key or "").strip()
        if user_key:
            return user_key
        return f"ticket:{job.ticket_id}"

    def _touch_conversation(
        self, *, job: SupportJob, reply: AgentReply, reply_at: str
    ) -> None:
        contact_label = self._contact_label(job)

        item = {
            "userKey": job.user_key,
            "contactLabel": contact_label,
            "ticketId": job.ticket_id,
            "threadId": job.thread_id,
            "channel": job.meta.channel or "",
            "lastMessageText": job.message.text,
            "lastReplyPreview": (reply.answer or "")[:240],
            "lastReplyAt": reply_at,
            "needsHandoff": reply.needs_handoff,
        }

        existing_index: int | None = None
        for idx, row in enumerate(self.recent_conversations):
            if (
                row.get("ticketId") == job.ticket_id
                and row.get("threadId") == job.thread_id
            ):
                existing_index = idx
                break

        if existing_index is not None:
            try:
                del self.recent_conversations[existing_index]
            except Exception:
                pass

        self.recent_conversations.appendleft(item)

    def conversations_snapshot(self) -> list[dict[str, Any]]:
        return list(self.recent_conversations)

    async def _runner(self) -> None:
        while self._running:
            try:
                async with self._condition:
                    await self._condition.wait_for(
                        lambda: not self._running
                        or ((not self.paused) and len(self.queue) > 0)
                    )
                    if not self._running:
                        break
                    task_id = self.queue.popleft()

                await self._process_task(task_id)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("AgentHub runner failed: %s", exc)
                self.last_error = str(exc)
                self.failed_today += 1
                self.status = "error"
                self.current_stage = "error"
                self._append_log(
                    level="error",
                    source="runtime",
                    message=f"Runner error: {exc}",
                    stage="error",
                )
                await self.broadcast(
                    {"type": "agent.state", "state": self.state_snapshot()}
                )

    async def _process_task(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        now = utc_iso()
        task["status"] = "running"
        task["stage"] = "preparing"
        task["startedAt"] = now

        self.status = "running"
        self.current_stage = "preparing"
        self.current_task_id = task_id
        self.current_task_title = task["title"]
        self.last_event_at = now
        self.last_heartbeat = now

        self._append_log(
            level="info",
            source="runtime",
            message=f"Task started: {task['title']}",
            task_id=task_id,
            stage="preparing",
        )

        await self.broadcast({"type": "task.started", "task": self.task_public(task)})
        await self.broadcast({"type": "agent.queue", "items": self.queue_snapshot()})
        await self.broadcast({"type": "agent.state", "state": self.state_snapshot()})

        async def emit_stage(
            stage: str, message: str, meta: dict[str, Any] | None = None
        ) -> None:
            task["stage"] = stage
            self.current_stage = stage
            self.last_event_at = utc_iso()
            self.last_heartbeat = self.last_event_at

            entry = {
                "timestamp": self.last_event_at,
                "level": "info",
                "source": "task",
                "taskId": task_id,
                "stage": stage,
                "message": message,
                "meta": meta or {},
            }
            self.logs.append(entry)

            await self.broadcast(
                {
                    "type": "task.stage",
                    "taskId": task_id,
                    "stage": stage,
                    "message": message,
                    "meta": meta or {},
                }
            )
            await self.broadcast(
                {"type": "agent.logs", "items": list(self.logs)[-200:]}
            )
            await self.broadcast(
                {"type": "agent.state", "state": self.state_snapshot()}
            )

        self._current_process_task = asyncio.create_task(
            self.orchestrator.process_office_task(
                title=task["title"],
                text=task["prompt"],
                stage_cb=emit_stage,
            )
        )

        try:
            reply = await self._current_process_task

            task["status"] = "completed"
            task["stage"] = "completed"
            task["finishedAt"] = utc_iso()
            task["answer"] = reply.answer
            task["answerPreview"] = (reply.answer or "")[:240]
            task["intent"] = reply.intent
            task["confidence"] = reply.confidence
            task["needsHandoff"] = reply.needs_handoff
            task["handoffReason"] = reply.handoff_reason
            task["tags"] = list(reply.tags)
            task["usedChunkIds"] = list(reply.used_chunk_ids)

            self.completed_today += 1
            self.last_answer_preview = task["answerPreview"]
            self._append_log(
                level="info",
                source="runtime",
                message=f"Task completed: {task['title']}",
                task_id=task_id,
                stage="completed",
            )

            self.history.appendleft(self.task_public(task))

            await self.broadcast(
                {"type": "task.completed", "task": self.task_public(task)}
            )
            await self.broadcast(
                {
                    "type": "task.output",
                    "taskId": task_id,
                    "output": {
                        "answer": reply.answer,
                        "intent": reply.intent,
                        "confidence": reply.confidence,
                        "needsHandoff": reply.needs_handoff,
                        "handoffReason": reply.handoff_reason,
                        "tags": reply.tags,
                        "usedChunkIds": reply.used_chunk_ids,
                    },
                }
            )

        except asyncio.CancelledError:
            task["status"] = "cancelled"
            task["stage"] = "cancelled"
            task["finishedAt"] = utc_iso()
            task["error"] = "Cancelled from UI"

            self._append_log(
                level="warning",
                source="runtime",
                message=f"Task cancelled: {task['title']}",
                task_id=task_id,
                stage="cancelled",
            )
            self.history.appendleft(self.task_public(task))
            await self.broadcast(
                {"type": "task.cancelled", "task": self.task_public(task)}
            )

        except Exception as exc:
            task["status"] = "failed"
            task["stage"] = "failed"
            task["finishedAt"] = utc_iso()
            task["error"] = str(exc)

            self.failed_today += 1
            self.last_error = str(exc)

            self._append_log(
                level="error",
                source="runtime",
                message=f"Task failed: {exc}",
                task_id=task_id,
                stage="failed",
            )
            self.history.appendleft(self.task_public(task))
            await self.broadcast(
                {"type": "task.failed", "task": self.task_public(task)}
            )

        finally:
            self._current_process_task = None
            self.current_task_id = None
            self.current_task_title = None
            self.last_heartbeat = utc_iso()

            if self.paused:
                self.status = "paused"
                self.current_stage = "paused"
            else:
                self.status = "idle"
                self.current_stage = "idle"

            await self.broadcast(
                {"type": "agent.queue", "items": self.queue_snapshot()}
            )
            await self.broadcast(
                {"type": "agent.history", "items": self.history_snapshot()}
            )
            await self.broadcast(
                {"type": "agent.logs", "items": list(self.logs)[-200:]}
            )
            await self.broadcast(
                {"type": "agent.state", "state": self.state_snapshot()}
            )

    def task_public(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": task["id"],
            "title": task["title"],
            "prompt": task["prompt"],
            "source": task["source"],
            "status": task["status"],
            "stage": task["stage"],
            "createdAt": task["createdAt"],
            "startedAt": task["startedAt"],
            "finishedAt": task["finishedAt"],
            "error": task["error"],
            "answerPreview": task["answerPreview"],
            "intent": task["intent"],
            "confidence": task["confidence"],
            "needsHandoff": task["needsHandoff"],
            "handoffReason": task["handoffReason"],
            "tags": task["tags"],
            "usedChunkIds": task["usedChunkIds"],
            "userKey": task.get("userKey"),
            "ticketId": task.get("ticketId"),
            "threadId": task.get("threadId"),
            "contactLabel": task.get("contactLabel"),
            "channel": task.get("channel"),
            "lastReplyAt": task.get("lastReplyAt"),
        }

    def queue_snapshot(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for task_id in self.queue:
            task = self.tasks.get(task_id)
            if task:
                items.append(self.task_public(task))
        if self.current_task_id:
            current = self.tasks.get(self.current_task_id)
            if current and current["status"] == "running":
                items.insert(0, self.task_public(current))
        return items

    def history_snapshot(self) -> list[dict[str, Any]]:
        return list(self.history)

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "connected": True,
            "status": self.status,
            "currentStage": self.current_stage,
            "currentTaskId": self.current_task_id,
            "currentTaskTitle": self.current_task_title,
            "queueSize": len(self.queue) + (1 if self.current_task_id else 0),
            "completedToday": self.completed_today,
            "failedToday": self.failed_today,
            "messagesSentToday": self.messages_sent_today,
            "paused": self.paused,
            "lastHeartbeat": self.last_heartbeat,
            "lastError": self.last_error,
            "lastAnswerPreview": self.last_answer_preview,
            "lastReplyAt": self.last_reply_at,
            "lastEventAt": self.last_event_at,
            "activeConversations": len(self.recent_conversations),
        }

    def _append_log(
        self,
        *,
        level: str,
        source: str,
        message: str,
        task_id: str | None = None,
        stage: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "timestamp": utc_iso(),
            "level": level,
            "source": source,
            "taskId": task_id,
            "stage": stage,
            "message": message,
            "meta": meta or {},
        }
        self.logs.append(entry)
        self.last_event_at = entry["timestamp"]

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for client in list(self.clients):
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)

        for client in dead:
            self.clients.discard(client)

