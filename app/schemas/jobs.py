from pydantic import BaseModel, Field
from typing import Any


class SupportJobMeta(BaseModel):
    lang_hint: str | None = None
    channel: str | None = None
    is_guest: bool = False


class SupportJobMessage(BaseModel):
    role: str = "user"
    text: str = Field(..., min_length=1)


class SupportJobHistoryItem(BaseModel):
    role: str
    text: str


class SupportJob(BaseModel):
    job_id: str
    ticket_id: str
    user_key: str
    thread_id: int
    message: SupportJobMessage
    history: list[SupportJobHistoryItem] = Field(default_factory=list)
    meta: SupportJobMeta = Field(default_factory=SupportJobMeta)


class ClaimJobResponse(BaseModel):
    ok: bool
    job: SupportJob | None = None
    raw: dict[str, Any] | None = None

