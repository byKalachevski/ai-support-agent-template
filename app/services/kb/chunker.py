from app.schemas.retrieval import KBChunk


def chunk_document(document: dict, max_chars: int = 1200) -> list[KBChunk]:
    text = document["text"]
    title = document["title"]
    lang = document.get("lang", "ru")
    category = document.get("category", "general")
    tags = document.get("tags", [])
    source = document.get("source", "")
    user_facing_links = document.get("user_facing_links", [])

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[KBChunk] = []

    buffer: list[str] = []
    current_len = 0
    index = 1

    for paragraph in paragraphs:
        p_len = len(paragraph)
        if buffer and current_len + p_len > max_chars:
            chunk_text = "\n".join(buffer).strip()
            chunks.append(
                KBChunk(
                    id=f"{document['id']}_chunk_{index}",
                    title=title,
                    lang=lang,
                    category=category,
                    tags=tags,
                    text=chunk_text,
                    source=source,
                    user_facing_links=user_facing_links,
                )
            )
            index += 1
            buffer = [paragraph]
            current_len = p_len
        else:
            buffer.append(paragraph)
            current_len += p_len

    if buffer:
        chunk_text = "\n".join(buffer).strip()
        chunks.append(
            KBChunk(
                id=f"{document['id']}_chunk_{index}",
                title=title,
                lang=lang,
                category=category,
                tags=tags,
                text=chunk_text,
                source=source,
                user_facing_links=user_facing_links,
            )
        )

    return chunks

