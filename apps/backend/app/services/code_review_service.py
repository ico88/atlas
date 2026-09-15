"""Code self-review service (self-improvement on ATLAS's own code, propose-only).

Walks ATLAS's source, runs deterministic checks (see
:mod:`app.maintenance.self_review`), and files each finding as a maintenance
issue (deduped, awaiting approval). It **never edits the repository**: the fix
step stays behind the existing human approval gate. This is what makes ATLAS
propose improvements to its own *code*, not only model swaps.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.maintenance import self_review as sr
from app.models.maintenance import IssueStatus, MaintenanceIssue

logger = logging.getLogger(__name__)

# Source trees ATLAS reviews (repo-relative). Kept narrow on purpose: our own
# first-party code, never dependencies or build output.
SCAN_DIRS = ["apps/backend/app", "services/node-agent/agent", "apps/frontend/src"]
_SKIP_PARTS = {"__pycache__", ".venv", "node_modules", ".next", "dist", "build"}
_SUFFIXES = {".py", ".ts", ".tsx"}


def repo_root() -> Path:
    """Repo root, from config override or discovered from this file's location.

    Walks upward looking for a directory that actually contains the source trees
    (``apps/backend``) or a ``.git`` marker, so self-review works regardless of
    how/where the package is installed. Falls back to the fixed relative depth.
    """

    override = get_settings().code_review_root
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "apps" / "backend").is_dir() or (parent / ".git").exists():
            return parent
    # …/apps/backend/app/services/code_review_service.py -> parents[4] == repo root
    return here.parents[4] if len(here.parents) > 4 else here.parent


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for sub in SCAN_DIRS:
        base = root / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.suffix not in _SUFFIXES:
                continue
            if any(part in _SKIP_PARTS for part in p.parts):
                continue
            files.append(p)
    return files


# Python packages to lint, as (package dir, source subdir). Each is linted with
# its OWN config, from inside its own directory, so findings match exactly what
# the project's CI enforces — not some other ruff's default ruleset.
_RUFF_PACKAGES = [("apps/backend", "app"), ("services/node-agent", "agent")]


def _ruff_binary() -> str | None:
    """The project's pinned ruff (next to the running interpreter) if present,
    else any ruff on PATH. Using the venv's ruff keeps the ruleset identical to CI."""

    candidate = Path(sys.executable).parent / "ruff"
    if candidate.is_file():
        return str(candidate)
    return shutil.which("ruff")


async def _run_ruff(root: Path) -> list[sr.Finding]:
    """Run ruff per package (each with its own config); [] if ruff isn't available."""

    ruff = _ruff_binary()
    if ruff is None:
        return []
    findings: list[sr.Finding] = []
    for pkg, src in _RUFF_PACKAGES:
        pkg_dir = root / pkg
        if not (pkg_dir / src).exists():
            continue
        try:
            proc = await asyncio.create_subprocess_exec(
                ruff,
                "check",
                "--output-format=json",
                src,
                cwd=str(pkg_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
        except OSError:
            continue
        try:
            payload = json.loads(out.decode() or "[]")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            findings.extend(sr.parse_ruff_json(payload, str(root)))
    return findings


async def scan(root: Path | None = None) -> tuple[list[sr.Finding], int]:
    """Collect all findings. Returns (findings, files_scanned)."""

    root = root or repo_root()
    settings = get_settings()
    findings: list[sr.Finding] = []
    files = _iter_source_files(root)
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(p.relative_to(root))
        findings.extend(sr.scan_markers(rel, text))
        findings.extend(sr.scan_long_file(rel, text, settings.code_review_long_file_lines))
    findings.extend(await _run_ruff(root))
    return sr.dedup(findings), len(files)


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


async def _upsert_issue(session: AsyncSession, finding: sr.Finding) -> bool:
    """Create or refresh the maintenance issue for a finding. Returns is-new."""

    fp = finding.signature()
    existing = (
        await session.execute(
            select(MaintenanceIssue).where(MaintenanceIssue.fingerprint == fp)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.occurrences += 1
        existing.sample = finding.sample()
        if existing.status in (IssueStatus.RESOLVED.value, IssueStatus.REJECTED.value):
            existing.status = IssueStatus.OPEN.value
        return False
    session.add(
        MaintenanceIssue(
            fingerprint=fp,
            title=finding.title(),
            service="self-review",
            severity=finding.severity,
            status=IssueStatus.OPEN.value,
            occurrences=1,
            sample=finding.sample(),
        )
    )
    return True


async def run_self_review(session: AsyncSession, root: Path | None = None) -> dict[str, int]:
    """Scan the code and file findings as maintenance issues (awaiting approval)."""

    findings, scanned = await scan(root)
    new = 0
    for f in findings:
        if await _upsert_issue(session, f):
            new += 1
    await session.commit()
    logger.info(
        "code self-review complete",
        extra={
            "event": "self_review_done",
            "context": {"scanned": scanned, "findings": len(findings), "new_issues": new},
        },
    )
    return {"scanned": scanned, "findings": len(findings), "new_issues": new}
