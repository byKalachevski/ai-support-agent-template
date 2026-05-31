from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.schemas.jobs import ClaimJobResponse, SupportJob
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BackendClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.BACKEND_API_TOKEN:
            headers["Authorization"] = f"Bearer {self.settings.BACKEND_API_TOKEN}"
        return headers

    def ws_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.BACKEND_API_TOKEN:
            headers["Authorization"] = f"Bearer {self.settings.BACKEND_API_TOKEN}"
        return headers

    def worker_ws_url(self) -> str:
        base_url = (self.settings.BACKEND_API_BASE_URL or "").strip().rstrip("/")
        if not base_url:
            return ""

        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"Unsupported BACKEND_API_BASE_URL scheme: {parsed.scheme}"
            )

        scheme = "wss" if parsed.scheme == "https" else "ws"
        path_prefix = parsed.path.rstrip("/")
        path = f"{path_prefix}{self.settings.WORKER_WS_PATH}"

        return f"{scheme}://{parsed.netloc}{path}"

    async def claim_job(self) -> ClaimJobResponse:
        if not self.settings.BACKEND_API_BASE_URL:
            return ClaimJobResponse(
                ok=False, job=None, raw={"reason": "missing_backend_api_base_url"}
            )

        url = f"{self.settings.BACKEND_API_BASE_URL}{self.settings.CLAIM_JOB_PATH}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={"worker_name": self.settings.WORKER_NAME},
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()

        raw_job = data.get("job")
        job = None

        if raw_job:
            payload = raw_job.get("payload") or {}

            if isinstance(payload, dict):
                payload = {
                    "job_id": raw_job.get("job_id"),
                    **payload,
                }
                job = SupportJob.model_validate(payload)

        return ClaimJobResponse(ok=bool(data.get("ok")), job=job, raw=data)

    async def complete_job(self, *, job_id: str, payload: dict) -> dict:
        url = f"{self.settings.BACKEND_API_BASE_URL}{self.settings.COMPLETE_JOB_PATH.format(job_id=job_id)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def fail_job(self, *, job_id: str, error: str) -> dict:
        url = f"{self.settings.BACKEND_API_BASE_URL}{self.settings.FAIL_JOB_PATH.format(job_id=job_id)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url, json={"error": error}, headers=self._headers()
            )
            response.raise_for_status()
            return response.json()

