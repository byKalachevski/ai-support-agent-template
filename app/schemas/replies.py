from pydantic import BaseModel, Field

from app.schemas.retrieval import KBLink


class AgentReply(BaseModel):
    answer: str
    intent: str
    confidence: float = 0.0
    needs_handoff: bool = False
    handoff_reason: str = ""
    tags: list[str] = Field(default_factory=list)
    used_chunk_ids: list[str] = Field(default_factory=list)
    links: list[KBLink] = Field(default_factory=list)


class AgentJobResult(BaseModel):
    ok: bool = True
    agent: str = "support-agent"
    job_id: str
    result: AgentReply

