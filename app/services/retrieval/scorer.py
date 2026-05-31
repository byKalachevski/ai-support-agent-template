from __future__ import annotations

import re


STOPWORDS = {
    "the",
    "a",
    "an",
    "what",
    "is",
    "about",
    "tell",
    "me",
    "how",
    "to",
}


INTENT_CATEGORY_HINTS = {
    "billing": ("05-subscription-and-billing",),
    "account_auth": ("04-account-and-auth",),
    "installation": ("09-download-and-platform-access", "03-onboarding"),
    "integration": ("06-automation-workflows", "08-product-features"),
    "troubleshooting": ("12-known-issues", "13-troubleshooting"),
    "security": ("11-security",),
    "operator_handoff": ("10-support-operations", "15-response-templates"),
    "product_overview": ("02-product-core", "08-product-features"),
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_\-]+", (text or "").lower())


def _filtered_query_tokens(text: str) -> set[str]:
    tokens = [token for token in tokenize(text) if len(token) > 1 and token not in STOPWORDS]
    if not tokens:
        tokens = [token for token in tokenize(text) if len(token) > 1]
    return set(tokens)


def score_chunk(
    *,
    query: str,
    title: str,
    text: str,
    tags: list[str],
    category: str,
    source: str,
    intent: str = "general",
) -> float:
    query_tokens = _filtered_query_tokens(query)
    if not query_tokens:
        return 0.0

    title_text = str(title or "")
    body_text = str(text or "")
    tag_text = " ".join(tags or [])
    category_text = str(category or "")
    source_text = str(source or "")

    title_tokens = set(tokenize(title_text))
    body_tokens = set(tokenize(body_text))
    tag_tokens = set(tokenize(tag_text))
    category_tokens = set(tokenize(category_text))
    source_tokens = set(tokenize(source_text))

    score = 0.0

    score += len(query_tokens & title_tokens) * 3.0
    score += len(query_tokens & tag_tokens) * 2.0
    score += len(query_tokens & category_tokens) * 1.5
    score += len(query_tokens & source_tokens) * 0.75
    score += len(query_tokens & body_tokens) * 1.0

    lowered_title = title_text.lower()
    lowered_body = body_text.lower()
    lowered_category = category_text.lower()
    lowered_source = source_text.lower()

    normalized_query = " ".join(sorted(query_tokens))
    if normalized_query and normalized_query in lowered_title:
        score += 2.0
    if normalized_query and normalized_query in lowered_body:
        score += 1.0

    for hinted_category in INTENT_CATEGORY_HINTS.get(intent, ()):
        hinted = hinted_category.lower()
        if hinted in lowered_category or hinted in lowered_source:
            score += 2.5

    if "readme.md" in lowered_source:
        score += 0.2

    return score
