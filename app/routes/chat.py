from fastapi import APIRouter, Request

from app.schemas.chat import ChatTestRequest, ChatTestResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/test", response_model=ChatTestResponse)
async def test_chat(payload: ChatTestRequest, request: Request) -> ChatTestResponse:
    orchestrator = request.app.state.support_orchestrator
    reply = await orchestrator.process_test_chat(payload)

    return ChatTestResponse(
        ok=True,
        answer=reply.answer,
        intent=reply.intent,
        confidence=reply.confidence,
        needs_handoff=reply.needs_handoff,
        handoff_reason=reply.handoff_reason,
        tags=reply.tags,
        used_chunk_ids=reply.used_chunk_ids,
        links=reply.links,
    )

