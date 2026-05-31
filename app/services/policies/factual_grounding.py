from __future__ import annotations

from app.schemas.replies import AgentReply
from app.schemas.retrieval import KBChunk


_DISCOVERY_PATTERNS = (
    "overview",
    "what is",
    "what can",
    "how does",
    "what else",
    "features",
    "capabilities",
)

_ENTITY_PATTERNS: dict[str, tuple[str, ...]] = {
    "account_auth": ("account", "login", "sign in", "auth", "authentication", "password"),
    "billing": ("billing", "subscription", "payment", "invoice", "refund", "pricing"),
    "installation": ("install", "download", "setup", "platform", "desktop", "app"),
    "troubleshooting": ("error", "issue", "problem", "bug", "broken", "not working", "troubleshoot"),
    "security": ("security", "privacy", "credential", "token", "api key", "secret"),
}


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(value in lowered for value in values)


def detect_entities(text: str) -> set[str]:
    lowered = (text or "").lower()
    found: set[str] = set()

    for entity, patterns in _ENTITY_PATTERNS.items():
        if _contains_any(lowered, patterns):
            found.add(entity)

    return found


def is_broad_discovery_query(text: str) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in _DISCOVERY_PATTERNS)


def build_deterministic_overview_reply(
    *, user_text: str, intent: str, chunks: list[KBChunk]
) -> AgentReply | None:
    if intent not in {"product_overview", "general"} and not is_broad_discovery_query(user_text):
        return None

    if not chunks:
        return None

    lines: list[str] = []
    used_chunk_ids: list[str] = []

    for chunk in chunks[:5]:
        title = (chunk.title or "").strip()
        if not title:
            continue
        lines.append(f"- {title}")
        used_chunk_ids.append(chunk.id)

    if not lines:
        return None

    answer = "Here are the most relevant knowledge-base topics:\n\n" + "\n".join(lines)

    return AgentReply(
        answer=answer,
        intent=intent,
        confidence=0.75,
        needs_handoff=False,
        tags=["deterministic_overview"],
        used_chunk_ids=used_chunk_ids,
        links=[],
    )


def validate_grounding(
    *, query: str, answer: str, chunks: list[KBChunk], intent: str
) -> tuple[bool, str]:
    normalized_answer = (answer or "").strip()
    if not normalized_answer:
        return False, "empty answer"

    if intent == "operator_handoff":
        return True, "ok"

    if not chunks:
        lowered = normalized_answer.lower()
        safe_fallback_markers = (
            "not enough information",
            "knowledge base does not contain",
            "i do not have enough context",
            "contact support",
            "operator",
        )
        if any(marker in lowered for marker in safe_fallback_markers):
            return True, "ok"
        return False, "answer has no retrieved grounding chunks"

    return True, "ok"
