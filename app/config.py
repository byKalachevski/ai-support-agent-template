from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "ai-support-agent-template"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8011
    LOG_LEVEL: str = "INFO"

    # Generic OpenAI-compatible LLM provider settings.
    LLM_PROVIDER: str = "generic"
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT_MS: int = 120000
    LLM_MAX_TOKENS: int = 900
    LLM_TEMPERATURE: float = 0.2
    LLM_JSON_MODE: bool = True

    KB_DIR: str = "kb"

    RUNS_DIR: str = "runs"
    LOGS_DIR: str = "logs"
    CACHE_DIR: str = "cache"

    SESSION_TTL_SECONDS: int = 300

    # Optional worker integration with an external backend.
    WORKER_ENABLED: bool = False
    WORKER_NAME: str = "ai-support-agent-worker-1"
    WORKER_WS_URL: str = ""
    WORKER_WS_PATH: str = "/internal/support-agent/ws"
    WORKER_RECONNECT_DELAY_SECONDS: int = 3
    WORKER_MAX_RECONNECT_DELAY_SECONDS: int = 30
    WORKER_WS_PING_INTERVAL_SECONDS: int = 20
    WORKER_WS_PING_TIMEOUT_SECONDS: int = 20

    # Optional backend API integration.
    BACKEND_API_BASE_URL: str = ""
    BACKEND_API_TOKEN: str = ""
    CLAIM_JOB_PATH: str = "/internal/support-agent/jobs/claim"
    COMPLETE_JOB_PATH: str = "/internal/support-agent/jobs/{job_id}/complete"
    FAIL_JOB_PATH: str = "/internal/support-agent/jobs/{job_id}/fail"
    HEARTBEAT_JOB_PATH: str = "/internal/support-agent/jobs/{job_id}/heartbeat"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

