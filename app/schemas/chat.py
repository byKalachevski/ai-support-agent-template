from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.retrieval import KBLink


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    text: str = Field(..., min_length=1)


class ChatTestRequest(BaseModel):
    text: str = Field(..., min_length=1)
    user_key: str = "local:test"
    ticket_id: str = "local-ticket"
    thread_id: int = 0
    lang_hint: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ChatTestResponse(BaseModel):
    ok: bool
    answer: str
    intent: str
    confidence: float
    needs_handoff: bool
    handoff_reason: str = ""
    tags: list[str] = Field(default_factory=list)
    used_chunk_ids: list[str] = Field(default_factory=list)
    links: list[KBLink] = Field(default_factory=list)

