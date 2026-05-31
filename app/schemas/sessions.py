from datetime import datetime

from pydantic import BaseModel, Field


class SessionState(BaseModel):
    session_key: str
    user_key: str
    ticket_id: str
    thread_id: int
    lang: str = "ru"

    last_intent: str = "general"
    summary: str = ""

    needs_handoff: bool = False
    handoff_status: str = (
        "bot_active"  # bot_active | handoff_requested | human_active | bot_resumed | closed
    )
    handoff_reason: str = ""
    handoff_requested_at: datetime | None = None
    handoff_locked: bool = False
    human_operator_id: str | None = None

    created_at: datetime
    updated_at: datetime
    recent_messages: list[dict] = Field(default_factory=list)

