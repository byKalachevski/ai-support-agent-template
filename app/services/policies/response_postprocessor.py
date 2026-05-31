from __future__ import annotations

import ast
import re

from app.schemas.replies import AgentReply
from app.schemas.retrieval import KBLink


_INTERNAL_JARGON_PATTERNS = (
    r"(?iu)\bintent\b",
    r"(?iu)\bchunk\b",
    r"(?iu)\bchunks\b",
    r"(?iu)\bkb\b",
    r"(?iu)\bgrounding\b",
    r"(?iu)\bpipeline\b",
    r"(?iu)\borchestrator\b",
    r"(?iu)\bpolicy\b",
)

_SERIALIZED_PREFIX_PATTERNS = (
    r"^\s*\{\s*['\"]text['\"]\s*:\s*['\"]",
    r"^\s*\{\s*['\"]answer['\"]\s*:\s*['\"]",
    r"^\s*\{\s*['\"]response['\"]\s*:\s*['\"]",
)

_SHORT_DEFINITION_PATTERNS = (
    "what is",
    "define",
    "explain",
    "overview",
)

_FUNCTIONS_PATTERNS = (
    "what can",
    "features",
    "capabilities",
    "how does it work",
)

_OPERATOR_HANDOFF_PATTERNS = (
    "human agent",
    "live agent",
    "operator",
    "transfer to operator",
    "transfer to human",
)


def _cleanup_serialized_dict_string(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                for key in ("answer", "text", "response", "message"):
                    value = parsed.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        except Exception:
            pass

    return raw


def _strip_internal_jargon(text: str) -> str:
    cleaned = text
    for pattern in _INTERNAL_JARGON_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(" \n\t-—:;,")


def _strip_bad_prefixes(text: str) -> str:
    cleaned = text.strip()

    for pattern in _SERIALIZED_PREFIX_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            cleaned = _cleanup_serialized_dict_string(cleaned)

    cleaned = re.sub(r"^(text|answer|response)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.strip("'\" ")
    return cleaned


def _normalize_punctuation(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"([,.!?;:])([^\s])", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _remove_meta_openers(text: str) -> str:
    cleaned = text.strip()
    meta_patterns = (
        r"(?iu)^based on the provided context[,.:;\s-]*",
        r"(?iu)^according to the knowledge base[,.:;\s-]*",
    )

    for pattern in meta_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    return cleaned.strip()


def _looks_like_short_definition(user_text: str, answer: str) -> bool:
    lowered_query = (user_text or "").lower()
    lowered_answer = (answer or "").lower()

    if any(pattern in lowered_query for pattern in _SHORT_DEFINITION_PATTERNS):
        return len(lowered_answer) <= 550

    return False


def _looks_like_functions_question(user_text: str) -> bool:
    lowered_query = (user_text or "").lower()
    return any(pattern in lowered_query for pattern in _FUNCTIONS_PATTERNS)


def _is_operator_handoff_request(user_text: str) -> bool:
    lowered_query = (user_text or "").lower()
    return any(pattern in lowered_query for pattern in _OPERATOR_HANDOFF_PATTERNS)


def _human_link_bucket(label: str, url: str) -> str:
    lowered = f"{label} {url}".lower()

    if "documentation" in lowered or "docs" in lowered or "help" in lowered:
        return "the documentation"
    if "download" in lowered or "install" in lowered:
        return "the download or installation page"
    if "billing" in lowered or "pricing" in lowered:
        return "the billing information"
    if "support" in lowered or "contact" in lowered:
        return "the support page"

    return "the linked materials"


def _build_details_sentence(links: list[KBLink]) -> str:
    if not links:
        return ""

    buckets: list[str] = []
    seen: set[str] = set()

    for link in links:
        bucket = _human_link_bucket(link.label, link.url)
        if bucket not in seen:
            seen.add(bucket)
            buckets.append(bucket)

    if not buckets:
        return ""

    if len(buckets) == 1:
        places = buckets[0]
    elif len(buckets) == 2:
        places = f"{buckets[0]} and {buckets[1]}"
    else:
        places = ", ".join(buckets[:-1]) + f", and {buckets[-1]}"

    return f"You can find more details in {places}."


def _append_contextual_details_sentence(*, user_text: str, answer: str, links: list[KBLink]) -> str:
    if not links:
        return answer

    if _is_operator_handoff_request(user_text):
        return answer

    if _looks_like_short_definition(user_text, answer) or _looks_like_functions_question(user_text):
        sentence = _build_details_sentence(links)
        if sentence and sentence.lower() not in answer.lower():
            return f"{answer}\n\n{sentence}"

    return answer


def postprocess_reply(*, user_text: str, reply: AgentReply) -> AgentReply:
    if reply.intent == "operator_handoff":
        reply.answer = (reply.answer or "").strip()
        return reply

    answer = reply.answer or ""

    answer = _cleanup_serialized_dict_string(answer)
    answer = _strip_bad_prefixes(answer)
    answer = _strip_internal_jargon(answer)
    answer = _remove_meta_openers(answer)
    answer = _normalize_punctuation(answer)

    if not answer:
        answer = "I do not have enough context in the knowledge base to answer confidently."

    answer = _append_contextual_details_sentence(
        user_text=user_text,
        answer=answer,
        links=reply.links,
    )

    reply.answer = answer
    return reply
