from fastapi import APIRouter, Request

from app.schemas.jobs import SupportJob
from app.services.reply.builder import build_job_result

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/process")
async def process_job(payload: SupportJob, request: Request) -> dict:
    orchestrator = request.app.state.support_orchestrator
    reply = await orchestrator.process_job(payload)
    return build_job_result(payload.job_id, reply).model_dump()

