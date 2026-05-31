from pathlib import Path

from app.config import Settings
from app.schemas.retrieval import KBChunk
from app.services.kb.normalizer import normalize_document
from app.services.kb.chunker import chunk_document
from app.utils.files import ensure_dirs
from app.utils.logger import get_logger

logger = get_logger(__name__)


class KBLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._chunks: list[KBChunk] = []

    @property
    def chunks(self) -> list[KBChunk]:
        return self._chunks

    def load(self) -> list[KBChunk]:
        ensure_dirs([self.settings.KB_DIR])

        kb_dir = Path(self.settings.KB_DIR)

        files = sorted(
            [
                p
                for p in kb_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in {".md", ".txt", ".html", ".htm"}
            ]
        )

        chunks: list[KBChunk] = []

        for path in files:
            raw_text = path.read_text(encoding="utf-8", errors="ignore")
            document = normalize_document(path, raw_text)

            rel_parts = path.relative_to(kb_dir).parts
            if rel_parts:
                top_folder = rel_parts[0]
                document["category"] = top_folder

            doc_chunks = chunk_document(document)
            chunks.extend(doc_chunks)

        self._chunks = chunks
        logger.info("KB loaded: files=%s chunks=%s", len(files), len(chunks))
        return chunks

