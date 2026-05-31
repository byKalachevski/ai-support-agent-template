from fastapi import APIRouter
from app.config import get_settings
from app.dependencies import get_kb_loader, get_llm_client, get_session_manager

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict:
    settings = get_settings()
    kb_loader = get_kb_loader()
    llm_client = get_llm_client()
    session_manager = get_session_manager()

    llm_ok = True
    llm_error = None
    try:
        await llm_client.ping()
    except Exception as exc:
        llm_ok = False
        llm_error = exc.__class__.__name__

    return {
        "ok": True,
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "llm_ok": llm_ok,
        "llm_error": llm_error,
        "kb_chunks": len(kb_loader.chunks),
        "sessions": session_manager.stats(),
        "worker_enabled": settings.WORKER_ENABLED,
        "worker_name": settings.WORKER_NAME,
    }

