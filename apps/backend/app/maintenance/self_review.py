"""Code self-review: ATLAS scans its OWN source for improvement opportunities.

This is the *code* side of self-improvement (distinct from choosing a better
model). It is deliberately **deterministic and honest** — no LLM guesswork — so
every finding points at a real line the user can verify:

* **lint** — `ruff` findings (0 on a clean tree; catches regressions);
* **marker** — `TODO` / `FIXME` / `HACK` / `XXX` left in the code;
* **long-file** — modules past a size threshold that are worth splitting.

Findings become maintenance issues (deduped by a stable signature) that sit
*awaiting approval*; nothing here edits the repository. The pure helpers below
are unit-tested; the repo walk / subprocess live in the service layer.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]?(.*)")


@dataclass
class Finding:
    kind: str  # lint / marker / long-file
    path: str  # repo-relative
    line: int
    code: str  # rule id / marker word / "size"
    message: str
    severity: str = "low"  # low / medium / high
    suggestion: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def signature(self) -> str:
        """Stable dedup key — excludes the line number so moving code that keeps
        the same issue does not spawn a duplicate."""

        key = "|".join(["self-review", self.kind, self.path, self.code, self.message[:80]])
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]

    def title(self) -> str:
        return f"[{self.kind}] {self.path}: {self.message[:120]}"

    def sample(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
            "source": "self-review",
            **self.extra,
        }


def scan_markers(path: str, text: str) -> list[Finding]:
    """Find TODO/FIXME/HACK/XXX markers in one file's text."""

    findings: list[Finding] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        # Only look at comment-ish lines to avoid matching the word in strings.
        if "#" not in raw and "//" not in raw and "*" not in raw:
            continue
        m = MARKER_RE.search(raw)
        if not m:
            continue
        word = m.group(1).upper()
        note = m.group(2).strip()
        sev = "medium" if word in {"FIXME", "HACK"} else "low"
        findings.append(
            Finding(
                kind="marker",
                path=path,
                line=i,
                code=word,
                message=f"{word}: {note}" if note else word,
                severity=sev,
                suggestion="Resolve or convert into a tracked task.",
            )
        )
    return findings


def scan_long_file(path: str, text: str, threshold: int) -> list[Finding]:
    """Flag a module that is longer than ``threshold`` lines."""

    n = text.count("\n") + 1 if text else 0
    if n <= threshold:
        return []
    return [
        Finding(
            kind="long-file",
            path=path,
            line=1,
            code="size",
            message=f"Module is {n} lines (> {threshold}); consider splitting.",
            severity="low",
            suggestion="Extract cohesive helpers into a submodule to ease review.",
            extra={"lines": n, "threshold": threshold},
        )
    ]


def parse_ruff_json(payload: list[dict[str, Any]], repo_root: str) -> list[Finding]:
    """Turn `ruff check --output-format=json` output into findings."""

    findings: list[Finding] = []
    for item in payload:
        filename = str(item.get("filename") or "")
        rel = _relativize(filename, repo_root)
        loc = item.get("location") or {}
        code = str(item.get("code") or "ruff")
        msg = str(item.get("message") or "").strip()
        findings.append(
            Finding(
                kind="lint",
                path=rel,
                line=int(loc.get("row") or 1),
                code=code,
                message=msg,
                severity="medium",
                suggestion="Apply the linter's fix (many are auto-fixable with `ruff --fix`).",
            )
        )
    return findings


def _relativize(filename: str, repo_root: str) -> str:
    root = repo_root.rstrip("/") + "/"
    return filename[len(root):] if filename.startswith(root) else filename


def dedup(findings: list[Finding]) -> list[Finding]:
    """Collapse findings with the same signature (keep first)."""

    seen: set[str] = set()
    out: list[Finding] = []
    for f in findings:
        sig = f.signature()
        if sig in seen:
            continue
        seen.add(sig)
        out.append(f)
    return out
