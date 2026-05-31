from __future__ import annotations

import httpx

from app.config import Settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Generic OpenAI-compatible chat-completions client.

    The public template intentionally avoids provider-specific names.
    Configure any compatible provider through LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _base_url(self) -> str:
        base_url = (self.settings.LLM_BASE_URL or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("LLM_BASE_URL is not configured.")
        return base_url

    def _headers(self) -> dict[str, str]:
        if not self.settings.LLM_API_KEY:
            raise ValueError("LLM_API_KEY is not configured.")

        return {
            "Authorization": f"Bearer {self.settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

    def _timeout_seconds(self) -> float:
        return max(self.settings.LLM_TIMEOUT_MS / 1000, 1)

    async def ping(self) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self._base_url()}/models",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def generate(
        self, *, system: str, prompt: str, temperature: float | None = None
    ) -> str:
        payload: dict = {
            "model": self.settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": (
                temperature
                if temperature is not None
                else self.settings.LLM_TEMPERATURE
            ),
            "max_tokens": self.settings.LLM_MAX_TOKENS,
        }

        if self.settings.LLM_JSON_MODE:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self._timeout_seconds()) as client:
            response = await client.post(
                f"{self._base_url()}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices or not isinstance(choices, list):
            raise ValueError("Empty choices response from LLM provider.")

        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty text response from LLM provider.")

        logger.info(
            "LLM response received from provider=%s model=%s",
            self.settings.LLM_PROVIDER,
            self.settings.LLM_MODEL,
        )
        return text

