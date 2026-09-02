"""HTML → title + plain text extraction (stdlib only, ROADMAP PR 15).

A small, tolerant ``html.parser`` based extractor. It drops script/style/noscript
content, collapses whitespace, and captures the ``<title>``. Pure and testable;
never executes scripts or fetches sub-resources.
"""

from __future__ import annotations

import contextlib
import re
from html.parser import HTMLParser

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
_BLOCK_TAGS = {
    "p", "br", "div", "section", "article", "li", "ul", "ol", "tr", "table",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "footer", "pre", "blockquote",
}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.text_parts.append(data)


def _collapse(text: str) -> str:
    # Collapse runs of spaces/tabs, then trim blank lines to at most one.
    text = re.sub(r"[ \t\f\v]+", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def extract_html(html: str) -> tuple[str, str]:
    """Return ``(title, text)`` extracted from an HTML string."""

    parser = _Extractor()
    with contextlib.suppress(Exception):  # malformed HTML must never raise
        parser.feed(html)
    title = _collapse("".join(parser.title_parts))
    text = _collapse("".join(parser.text_parts))
    return title, text


def snippet(text: str, query: str, length: int = 280) -> str:
    """A short excerpt of ``text`` centred on the first query term hit."""

    if not text:
        return ""
    terms = [t for t in re.split(r"\W+", query.lower()) if t]
    low = text.lower()
    pos = -1
    for term in terms:
        pos = low.find(term)
        if pos != -1:
            break
    if pos == -1:
        return text[:length].strip()
    start = max(0, pos - length // 3)
    end = min(len(text), start + length)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"
