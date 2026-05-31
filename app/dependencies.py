from functools import lru_cache

from app.config import get_settings
from app.services.kb.loader import KBLoader
from app.services.llm.client import LLMClient
from app.services.retrieval.search import RetrievalService
from app.services.sessions.manager import SessionManager


@lru_cache
def get_kb_loader() -> KBLoader:
    settings = get_settings()
    return KBLoader(settings)


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    return LLMClient(settings)


@lru_cache
def get_retrieval_service() -> RetrievalService:
    settings = get_settings()
    return RetrievalService(settings)


@lru_cache
def get_session_manager() -> SessionManager:
    settings = get_settings()
    return SessionManager(ttl_seconds=settings.SESSION_TTL_SECONDS)

