from __future__ import annotations

from typing import Iterable

from app.schemas.retrieval import KBChunk, KBLink

NAVIGATION_KEYWORDS = (
    "open",
    "download",
    "link",
)

ACTION_INTENTS = {
    "installation",
    "integration",
    "account_auth",
    "billing",
    "troubleshooting",
}

OVERVIEW_LINK_INTENTS = {
    "product_overview",
    "faq",
    "general",
}

LINK_WORTHY_CATEGORIES = {
    "02-product-core",
    "03-onboarding",
    "04-account-and-auth",
    "05-subscription-and-billing",
    "09-download-and-platform-access",
    "10-support-operations",
    "13-troubleshooting",
}

ANSWER_LINK_HINTS = (
    "documentation",
    "help center",
    "blog",
    "site",
    "browser",
)


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def _chunk_has_user_links(chunk: KBChunk) -> bool:
    return bool(chunk.user_facing_links)


def _normalize_url(url: str) -> str:
    return str(url or "").strip().rstrip("/").lower()


def should_force_links(
    *,
    user_text: str,
    answer_text: str,
    intent: str,
    chunks: list[KBChunk],
) -> bool:
    user_lower = (user_text or "").lower()
    answer_lower = (answer_text or "").lower()

    if _contains_any(user_lower, NAVIGATION_KEYWORDS):
        return True

    if intent in ACTION_INTENTS:
        return True

    if _contains_any(answer_lower, ANSWER_LINK_HINTS):
        return True

    if any(
        (chunk.category or "").strip() in LINK_WORTHY_CATEGORIES for chunk in chunks
    ):
        return True

    if intent in OVERVIEW_LINK_INTENTS and any(
        _chunk_has_user_links(chunk) for chunk in chunks
    ):
        return True

    return False


def _ordered_chunks(chunks: list[KBChunk], used_chunk_ids: list[str]) -> list[KBChunk]:
    preferred_chunks: list[KBChunk] = []
    used_set = set(used_chunk_ids or [])

    if used_set:
        preferred_chunks.extend([chunk for chunk in chunks if chunk.id in used_set])
        preferred_chunks.extend([chunk for chunk in chunks if chunk.id not in used_set])
    else:
        preferred_chunks = list(chunks)

    return preferred_chunks


def _push_link(collected: list[KBLink], seen: set[str], link: KBLink) -> None:
    normalized = _normalize_url(link.url)
    if not normalized or normalized in seen:
        return
    seen.add(normalized)
    collected.append(link)


def choose_primary_links(
    *,
    chunks: list[KBChunk],
    used_chunk_ids: list[str],
    intent: str,
    user_text: str = "",
    limit: int = 2,
) -> list[KBLink]:
    preferred_chunks = _ordered_chunks(chunks, used_chunk_ids)
    collected: list[KBLink] = []
    seen: set[str] = set()

    for chunk in preferred_chunks:
        links = chunk.user_facing_links or []

        primary_links = [
            link for link in links if (link.group or "").strip() == "primary"
        ]
        secondary_links = [
            link for link in links if (link.group or "").strip() == "secondary"
        ]

        for link in primary_links:
            _push_link(collected, seen, link)

        for link in secondary_links:
            _push_link(collected, seen, link)

        if len(collected) >= limit:
            return collected[:limit]

    return collected[:limit]

