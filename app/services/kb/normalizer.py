from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup


def detect_lang_from_path(path: str) -> str:
    lowered = path.lower()
    if (
        "/en/" in lowered
        or lowered.endswith("_en.html")
        or lowered.endswith("_en.txt")
        or lowered.endswith(".en.md")
    ):
        return "en"
    return "ru"


def _split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    text = raw_text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, raw_text

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw_text

    closing_index: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_index = idx
            break

    if closing_index is None:
        return {}, raw_text

    frontmatter_raw = "\n".join(lines[1:closing_index]).strip()
    body = "\n".join(lines[closing_index + 1 :]).strip()

    if not frontmatter_raw:
        return {}, body

    try:
        parsed = yaml.safe_load(frontmatter_raw) or {}
    except Exception:
        parsed = {}

    if not isinstance(parsed, dict):
        parsed = {}

    return parsed, body


def _as_clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    return []


def _normalize_user_facing_links(meta: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    user_facing_links = meta.get("user_facing_links") or {}

    def push(url: str, label: str, group: str) -> None:
        clean_url = str(url).strip()
        clean_label = str(label).strip()
        clean_group = str(group).strip() or "primary"

        if not clean_url:
            return
        if clean_url in seen_urls:
            return

        seen_urls.add(clean_url)
        result.append(
            {
                "label": clean_label or clean_url,
                "url": clean_url,
                "group": clean_group,
            }
        )

    if isinstance(user_facing_links, dict):
        for group_name, items in user_facing_links.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    push(
                        url=item.get("url", ""),
                        label=item.get("label", "") or item.get("url", ""),
                        group=str(group_name),
                    )
                elif isinstance(item, str):
                    push(url=item, label=item, group=str(group_name))
    elif isinstance(user_facing_links, list):
        for item in user_facing_links:
            if isinstance(item, dict):
                push(
                    url=item.get("url", ""),
                    label=item.get("label", "") or item.get("url", ""),
                    group=item.get("group", "primary"),
                )
            elif isinstance(item, str):
                push(url=item, label=item, group="primary")

    return result


def normalize_document(path: Path, raw_text: str) -> dict:
    suffix = path.suffix.lower()
    meta: dict[str, Any] = {}
    body_text = raw_text
    title = path.stem

    if suffix == ".md":
        meta, body_text = _split_frontmatter(raw_text)
        if meta.get("title"):
            title = str(meta["title"]).strip() or title
    elif suffix in {".html", ".htm"}:
        soup = BeautifulSoup(raw_text, "lxml")
        if soup.title and soup.title.text.strip():
            title = soup.title.text.strip()
        body_text = soup.get_text("\n", strip=True)

    text = "\n".join(line.strip() for line in body_text.splitlines() if line.strip())

    category = str(meta.get("category") or "general").strip() or "general"
    lang = str(meta.get("lang") or detect_lang_from_path(str(path))).strip() or "ru"

    tags: list[str] = []
    tags.extend(_as_clean_list(meta.get("tags")))
    tags.extend(_as_clean_list(meta.get("keywords")))
    tags.extend(_as_clean_list(meta.get("intents")))

    dedup_tags: list[str] = []
    seen_tags: set[str] = set()
    for tag in tags:
        key = tag.lower()
        if key in seen_tags:
            continue
        seen_tags.add(key)
        dedup_tags.append(tag)

    return {
        "id": path.stem,
        "title": title,
        "lang": lang,
        "category": category,
        "tags": dedup_tags,
        "text": text,
        "source": str(path),
        "user_facing_links": _normalize_user_facing_links(meta),
    }

