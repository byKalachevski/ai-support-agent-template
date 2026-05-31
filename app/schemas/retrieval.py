from pydantic import BaseModel, Field


class KBLink(BaseModel):
    label: str
    url: str
    group: str = "primary"


class KBChunk(BaseModel):
    id: str
    title: str
    lang: str = "ru"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    text: str
    source: str = ""
    score: float = 0.0
    user_facing_links: list[KBLink] = Field(default_factory=list)

