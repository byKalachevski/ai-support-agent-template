from __future__ import annotations

import re

from app.schemas.replies import AgentReply
from app.schemas.retrieval import KBLink


_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TRAILING_URL_PUNCT = '.,;:!?)]}>\'"'
_ALLOWED_LINK_GROUPS = {"primary", "secondary"}


def _normalize_url(value: str) -> str:
    clean = str(value or "").strip()

    while clean and clean[-1] in _TRAILING_URL_PUNCT:
        clean = clean[:-1]

    return clean.rstrip("/").strip()


def _normalize_group(value: str | None) -> str:
    group = str(value or "primary").strip().lower() or "primary"
    return group if group in _ALLOWED_LINK_GROUPS else "primary"


def _normalize_product_names(text: str) -> str:
    return str(text or "")


def _cleanup_answer_text(text: str) -> str:
    result = str(text or "").replace("\u00A0", " ").strip()

    if not result:
        return ""

    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"([,.;:!?])([^\s\n])", r"\1 \2", result)

    cleaned_lines: list[str] = []
    prev_blank = False

    for raw_line in result.splitlines():
        line = raw_line.strip()

        if not line:
            if not prev_blank and cleaned_lines:
                cleaned_lines.append("")
            prev_blank = True
            continue

        if re.fullmatch(r"[-:.,;!?()\[\]{}\s]+", line):
            continue

        cleaned_lines.append(line)
        prev_blank = False

    return "\n".join(cleaned_lines).strip()


def _sanitize_reply_links(links: list[KBLink] | None, limit: int = 4) -> list[KBLink]:
    result: list[KBLink] = []
    seen_urls: set[str] = set()

    for link in links or []:
        normalized = _normalize_url(getattr(link, "url", ""))
        if not normalized or normalized in seen_urls:
            continue

        seen_urls.add(normalized)
        result.append(
            KBLink(
                label=(getattr(link, "label", None) or normalized).strip(),
                url=normalized,
                group=_normalize_group(getattr(link, "group", None)),
            )
        )

        if len(result) >= limit:
            break

    return result


def _translate_link_title_en(value: str) -> str:
    return str(value or "").strip()


def _localize_link_label(label: str, lang: str) -> str:
    raw = str(label or "").strip()
    if not raw:
        return raw

    return _translate_link_title_en(raw)


def _localize_reply_links(
    links: list[KBLink] | None, lang: str, limit: int = 4
) -> list[KBLink]:
    result: list[KBLink] = []

    for link in _sanitize_reply_links(links, limit=limit):
        result.append(
            KBLink(
                label=_localize_link_label(link.label, lang),
                url=link.url,
                group=link.group,
            )
        )

    return result


def _remove_duplicated_link_urls(answer: str, reply: AgentReply) -> str:
    text = str(answer or "").strip()
    if not text or not reply.links:
        return text

    known_urls = {
        _normalize_url(link.url)
        for link in reply.links
        if getattr(link, "url", None)
    }
    known_urls.discard("")

    if not known_urls:
        return text

    def _replace_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        normalized = _normalize_url(raw_url)
        if normalized in known_urls:
            return ""
        return raw_url

    text = _URL_RE.sub(_replace_url, text)
    return _cleanup_answer_text(text)


def apply_support_policy(reply: AgentReply, lang: str = "en") -> AgentReply:
    reply.links = _localize_reply_links(reply.links, lang=lang, limit=4)
    reply.answer = _normalize_product_names(_remove_duplicated_link_urls(reply.answer, reply))

    if reply.intent == "operator_handoff":
        if not reply.answer.strip():
            reply.answer = (
                "I am transferring the conversation to a human operator. "
                "You can describe the issue in one message while you wait."
            )
        reply.needs_handoff = True
        if not reply.handoff_reason:
            reply.handoff_reason = "user_requested_operator"
        reply.confidence = max(reply.confidence, 0.98)
        return reply

    if not reply.answer.strip():
        if reply.links:
            reply.answer = "I have attached the relevant materials below."
            reply.needs_handoff = False
            if reply.handoff_reason == "empty_answer":
                reply.handoff_reason = ""
            reply.confidence = max(reply.confidence, 0.55)
            return reply

        reply.answer = (
            "I could not prepare a confident answer from the available knowledge base. "
            "Please add more documentation or route this conversation to a human operator."
        )
        reply.needs_handoff = True
        if not reply.handoff_reason:
            reply.handoff_reason = "empty_answer"
        reply.confidence = min(reply.confidence, 0.2)

    return reply
