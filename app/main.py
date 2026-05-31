from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.dependencies import (
    get_kb_loader,
    get_llm_client,
    get_retrieval_service,
    get_session_manager,
)
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.routes.jobs import router as jobs_router
from app.routes.ws import router as ws_router
from app.services.orchestrator import SupportOrchestrator
from app.services.prod.client import BackendClient
from app.services.runtime.hub import AgentHub
from app.services.worker import WorkerService
from app.utils.files import ensure_dirs
from app.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)
worker_service: WorkerService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    ensure_dirs(
        [
            settings.KB_DIR,
            settings.RUNS_DIR,
            settings.LOGS_DIR,
            settings.CACHE_DIR,
        ]
    )

    kb_loader = get_kb_loader()
    kb_loader.load()

    orchestrator = SupportOrchestrator(
        kb_loader=kb_loader,
        retrieval_service=get_retrieval_service(),
        llm_client=get_llm_client(),
        session_manager=get_session_manager(),
    )

    support_hub = AgentHub(orchestrator=orchestrator)
    await support_hub.start()

    app.state.support_orchestrator = orchestrator
    app.state.support_hub = support_hub

    global worker_service
    worker_service = WorkerService(
        settings=settings,
        orchestrator=orchestrator,
        prod_client=BackendClient(settings),
        hub=support_hub,
    )
    await worker_service.start()

    logger.info("Support agent started")
    yield

    if worker_service:
        await worker_service.stop()

    await support_hub.stop()
    logger.info("Support agent stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/")
    async def root() -> dict:
        return {
            "ok": True,
            "service": settings.APP_NAME,
            "message": "Support agent API is running",
        }

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(jobs_router)
    app.include_router(ws_router)

    return app


app = create_app()

