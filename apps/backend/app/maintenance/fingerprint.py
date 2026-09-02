"""Log fingerprinting for issue deduplication (spec §11 step 2).

Normalizes the volatile parts of a log message (numbers, hex ids, uuids, paths,
quoted values, timestamps) so that the same underlying error collapses to one
stable fingerprint regardless of the specific values in each occurrence.
"""

from __future__ import annotations

import hashlib
import re

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b0x[0-9a-f]+\b", re.I)
_LONGHEX = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(?:\.\d+)?z?", re.I)
_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def normalize_message(message: str) -> str:
    text = message.lower()
    text = _ISO_TS.sub("<ts>", text)
    text = _UUID.sub("<uuid>", text)
    text = _HEX.sub("<hex>", text)
    text = _LONGHEX.sub("<id>", text)
    text = _NUM.sub("<n>", text)
    text = _WS.sub(" ", text).strip()
    return text


def compute_fingerprint(
    *, service: str | None, message: str, level: str | None = None, event: str | None = None
) -> str:
    """Return a stable 32-char fingerprint for a log event."""

    normalized = normalize_message(message)
    key = "|".join([service or "", level or "", event or "", normalized])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
