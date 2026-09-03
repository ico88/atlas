"""Automatic memory capture from chat (heuristic, offline).

Extracts durable, self-referential facts from a user message so the assistant
can "remember" them across conversations — e.g. "sono Federico" →
"The user's name is Federico". Conservative on purpose: only high-confidence
patterns (IT + EN) are captured, to avoid polluting memory with noise.

Pure functions (take text) so they are unit-testable without a model.
"""

from __future__ import annotations

import re

# Name: require the captured token to be Capitalized (a proper noun), so
# "sono Federico" matches but "sono stanco" / "i am tired" do not.
_NAME = re.compile(
    r"\b(?i:mi chiamo|il mio nome è|my name is|i am|i'm|sono)\s+([A-ZÀ-Ý][\wà-ÿ'’-]{1,40})",
)
_REMEMBER = re.compile(r"\b(?:ricorda(?:ti)? che|remember that)\s+(.+)", re.IGNORECASE)
_PREFER = re.compile(r"\b(?:preferisco|i prefer)\s+(.+)", re.IGNORECASE)
# "il mio <thing> è <value>" / "my <thing> is <value>"
_ATTR = re.compile(
    r"\b(?:il mio|la mia|my)\s+([\wà-ÿ' -]{2,30}?)\s+(?:è|is)\s+(.+)",
    re.IGNORECASE,
)

_STOP_NAMES = {"stanco", "stanca", "sicuro", "certo", "qui", "pronto", "tired", "sure", "here"}


def _clean(text: str) -> str:
    return text.strip().rstrip(".!?，,").strip()


def extract_facts(text: str) -> list[str]:
    """Return a list of durable fact statements found in ``text`` (may be empty)."""

    facts: list[str] = []
    if not text or len(text) > 2000:
        return facts

    m = _NAME.search(text)
    if m and m.group(1).lower() not in _STOP_NAMES:
        facts.append(f"The user's name is {_clean(m.group(1))}")

    m = _REMEMBER.search(text)
    if m:
        facts.append(_clean(m.group(1)))

    m = _PREFER.search(text)
    if m:
        facts.append(f"The user prefers {_clean(m.group(1))}")

    m = _ATTR.search(text)
    if m:
        thing = _clean(m.group(1))
        value = _clean(m.group(2))
        # Skip the name attribute (handled above) and overly long values.
        if thing.lower() not in ("nome", "name") and len(value) <= 120:
            facts.append(f"The user's {thing} is {value}")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for f in facts:
        key = f.lower()
        if f and key not in seen:
            seen.add(key)
            out.append(f)
    return out
