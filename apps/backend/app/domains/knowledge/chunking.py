"""Text chunking for indexing (spec §6 RAG)."""

from __future__ import annotations

from app.core.config import get_settings


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Split text into overlapping character windows, preferring paragraph breaks."""

    settings = get_settings()
    size = size or settings.rag_chunk_size
    overlap = overlap if overlap is not None else settings.rag_chunk_overlap
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        # Try to break on a paragraph/sentence boundary near the window end.
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", "\n", ". "):
                idx = window.rfind(sep)
                if idx > size // 2:
                    end = start + idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
