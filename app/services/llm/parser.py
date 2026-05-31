from __future__ import annotations

import ast
import json
import re
from typing import Any

from app.schemas.replies import AgentReply
from app.schemas.retrieval import KBLink

_TRAILING_URL_PUNCT = ".,;:!?)]}>\"'"
_ALLOWED_LINK_GROUPS = {"primary", "secondary"}


def strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def extract_json_object(text: str) -> dict:
    cleaned = strip_code_fences(text)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        object_text = match.group(0)

        try:
            data = json.loads(object_text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        try:
            data = ast.literal_eval(object_text)
            if isinstance(data, dict):
                return data
        except (ValueError, SyntaxError):
            pass

    try:
        data = ast.literal_eval(cleaned)
        if isinstance(data, dict):
            return data
    except (ValueError, SyntaxError):
        pass

    raise ValueError("LLM response does not contain a valid JSON/dict object.")


def _normalize_url(value: Any) -> str:
    clean = str(value or "").strip()

    while clean and clean[-1] in _TRAILING_URL_PUNCT:
        clean = clean[:-1]

    return clean.rstrip("/").strip()


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    if isinstance(value, bool):
        return 1.0 if value else 0.0

    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))

    if isinstance(value, str):
        cleaned = value.strip().lower()
        if not cleaned:
            return default

        alias_map = {
            "low": 0.25,
            "medium": 0.55,
            "med": 0.55,
            "mid": 0.55,
            "high": 0.85,
        }
        if cleaned in alias_map:
            return alias_map[cleaned]

        if cleaned.endswith("%"):
            numeric_part = cleaned[:-1].strip().replace(",", ".")
            try:
                return max(0.0, min(float(numeric_part) / 100.0, 1.0))
            except ValueError:
                return default

        cleaned = cleaned.replace(",", ".")
        try:
            return max(0.0, min(float(cleaned), 1.0))
        except ValueError:
            return default

    return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        cleaned = value.strip().lower()
        if not cleaned:
            return default

        if cleaned in {"true", "1", "yes", "y", "on"}:
            return True

        if cleaned in {"false", "0", "no", "n", "off"}:
            return False

    return default


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []

    return []


def _coerce_links(value: Any) -> list[KBLink]:
    if value is None:
        return []

    result: list[KBLink] = []
    seen_urls: set[str] = set()

    def push(url: str, label: str = "", group: str = "primary") -> None:
        clean_url = _normalize_url(url)
        clean_label = str(label).strip()
        clean_group = str(group).strip().lower() or "primary"
        if clean_group not in _ALLOWED_LINK_GROUPS:
            clean_group = "primary"

        if not clean_url or clean_url in seen_urls:
            return

        seen_urls.add(clean_url)
        result.append(
            KBLink(
                label=clean_label or clean_url,
                url=clean_url,
                group=clean_group,
            )
        )

    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                push(
                    url=item.get("url", ""),
                    label=item.get("label", ""),
                    group=item.get("group", "primary"),
                )
            elif isinstance(item, str):
                push(url=item, label=item)
    elif isinstance(value, dict):
        for group_name, items in value.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        push(
                            url=item.get("url", ""),
                            label=item.get("label", ""),
                            group=group_name,
                        )
                    elif isinstance(item, str):
                        push(url=item, label=item, group=group_name)

    return result


def _extract_answer(data: dict[str, Any]) -> str:
    for key in ("answer", "text", "response", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        for key in ("answer", "text", "response", "message"):
            value = nested_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def parse_agent_reply(text: str) -> AgentReply:
    data = extract_json_object(text)

    return AgentReply(
        answer=_extract_answer(data),
        intent=str(data.get("intent", "general")).strip() or "general",
        confidence=_coerce_float(data.get("confidence", 0.0), default=0.0),
        needs_handoff=_coerce_bool(data.get("needs_handoff", False), default=False),
        handoff_reason=str(data.get("handoff_reason", "")).strip(),
        tags=_coerce_str_list(data.get("tags")),
        used_chunk_ids=_coerce_str_list(data.get("used_chunk_ids")),
        links=_coerce_links(data.get("links")),
    )
