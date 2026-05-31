from app.config import Settings
from app.schemas.retrieval import KBChunk
from app.services.retrieval.scorer import score_chunk
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RetrievalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(
        self,
        *,
        query: str,
        chunks: list[KBChunk],
        lang: str = "ru",
        intent: str = "general",
        top_k: int = 5,
    ) -> list[KBChunk]:
        scored: list[KBChunk] = []

        for chunk in chunks:
            score = score_chunk(
                query=query,
                title=chunk.title,
                text=chunk.text,
                tags=chunk.tags,
                category=chunk.category,
                source=chunk.source,
                intent=intent,
            )

            if chunk.lang == lang:
                score += 0.1

            if score <= 0:
                continue

            data = chunk.model_dump()
            data["score"] = round(score, 4)
            scored.append(KBChunk(**data))

        scored.sort(key=lambda item: item.score, reverse=True)
        result = scored[:top_k]
        logger.info(
            "Retrieval completed",
            extra={
                "found": len(result),
                "lang": lang,
                "intent": intent,
            },
        )
        return result

