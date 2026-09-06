"""Chat attachment handling: extract text from an uploaded file and feed it to
the model as context (chat file upload).

Supported without extra services: plain text, Markdown, CSV/TSV, JSON, and source
code (decoded as UTF-8, latin-1 fallback). PDFs are extracted with ``pypdf`` when
available. The raw bytes are never stored — only the extracted text — and both the
per-file size and the total context injected per turn are bounded.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment

logger = logging.getLogger(__name__)

MAX_BYTES = 5_000_000  # 5 MB per file
MAX_TEXT_CHARS = 200_000  # cap stored text per file
MAX_CONTEXT_CHARS = 12_000  # cap total attachment text injected into one turn

# Extensions we confidently decode as UTF-8 text.
_TEXT_EXTS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "yaml", "yml", "toml", "ini",
    "log", "py", "js", "ts", "tsx", "jsx", "java", "c", "h", "cpp", "hpp", "cs",
    "go", "rs", "rb", "php", "sh", "bash", "sql", "html", "css", "xml", "env",
}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _extract_pdf(raw: bytes) -> tuple[str, str | None]:
    try:
        import io

        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return "", "PDF non supportato su questo server (pypdf non installato)."
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [(p.extract_text() or "") for p in reader.pages]
        return "\n\n".join(pages).strip(), None
    except Exception as exc:  # noqa: BLE001 - malformed PDF, never crash the request
        return "", f"Impossibile leggere il PDF: {exc}"


def extract_text(filename: str, content_type: str | None, raw: bytes) -> tuple[str, str | None]:
    """Return (text, error). A non-empty error means extraction failed/unsupported."""

    if len(raw) > MAX_BYTES:
        return "", f"File troppo grande (max {MAX_BYTES // 1_000_000} MB)."
    ext = _ext(filename)
    ctype = (content_type or "").lower()

    if ext == "pdf" or ctype == "application/pdf":
        text, err = _extract_pdf(raw)
    elif ext in _TEXT_EXTS or ctype.startswith("text/") or "json" in ctype or "xml" in ctype:
        text, err = _decode(raw), None
    else:
        # Try a best-effort text decode; reject if it looks binary.
        decoded = _decode(raw)
        if "\x00" in decoded[:4096]:
            return "", f"Tipo di file non supportato: .{ext or '?'} (usa testo, codice o PDF)."
        text, err = decoded, None

    if err:
        return "", err
    text = text.strip()
    if not text:
        return "", "Nessun testo estraibile dal file."
    return text[:MAX_TEXT_CHARS], None


async def create_attachment(
    session: AsyncSession,
    *,
    filename: str,
    content_type: str | None,
    raw: bytes,
    conversation_id: str | None = None,
) -> tuple[Attachment | None, str | None]:
    text, err = extract_text(filename, content_type, raw)
    if err:
        return None, err
    att = Attachment(
        conversation_id=conversation_id,
        filename=filename[:255],
        content_type=(content_type or None),
        size_bytes=len(raw),
        text_content=text,
    )
    session.add(att)
    await session.commit()
    await session.refresh(att)
    logger.info(
        "attachment stored",
        extra={"event": "attachment_add", "context": {"file": att.filename, "chars": len(text)}},
    )
    return att, None


async def get_many(session: AsyncSession, ids: list[str]) -> list[Attachment]:
    if not ids:
        return []
    rows = await session.execute(select(Attachment).where(Attachment.id.in_(ids)))
    by_id = {a.id: a for a in rows.scalars().all()}
    return [by_id[i] for i in ids if i in by_id]  # preserve caller order


def build_context(attachments: list[Attachment]) -> str:
    """Build a bounded system-context block from attachment texts."""

    if not attachments:
        return ""
    parts = ["The user attached the following file(s). Use them to answer:"]
    budget = MAX_CONTEXT_CHARS
    for att in attachments:
        if budget <= 0:
            break
        chunk = att.text_content[:budget]
        budget -= len(chunk)
        truncated = " (truncated)" if len(att.text_content) > len(chunk) else ""
        parts.append(f"\n--- FILE: {att.filename}{truncated} ---\n{chunk}")
    return "\n".join(parts)
