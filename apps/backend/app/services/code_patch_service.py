"""LLM code-patch pipeline — ATLAS writes the actual fix for its own code.

This is the step beyond self-review: given a code finding, a **code-capable local
model** is asked to rewrite the affected file, the result is checked (syntax +
real sandbox) and turned into a maintenance fix awaiting approval. It is
**propose-only** — the patch is never merged; a human approves it, and only then
does the maintenance flow open the PR.

Honesty by construction:

* if no coder model is available, the request **fails** instead of faking a patch;
* the model's output must parse, differ from the original, and (for Python) still
  compile — otherwise it is rejected, never proposed;
* the patch is validated in the same isolated sandbox as any other fix.

The parsing/diff/validation helpers are pure and unit-tested; the model call and
DB writes live in the async entry point.
"""

from __future__ import annotations

import ast
import difflib
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import router
from app.ai.base import ChatMessage
from app.ai.echo import ECHO_MODEL
from app.core.config import get_settings
from app.models.maintenance import MaintenanceIssue, MaintenanceRun
from app.models.provider import LLMModel
from app.services import code_review_service, maintenance_service

logger = logging.getLogger(__name__)

# Model names that indicate coding capability (substring match, case-insensitive).
_CODER_HINTS = ("coder", "code-", "codellama", "starcoder", "deepseek-coder", "devstral")

_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)


class CodePatchError(RuntimeError):
    pass


# --- pure helpers -----------------------------------------------------------


def is_coder_model(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _CODER_HINTS)


def build_messages(path: str, content: str, finding: dict) -> list[ChatMessage]:
    """Prompt asking the model to return the corrected FULL file in one block."""

    line = finding.get("line")
    where = f" (around line {line})" if line else ""
    system = (
        "You are a senior Python/TypeScript engineer fixing a codebase. "
        "You output only the corrected file, nothing else."
    )
    user = (
        f"File: {path}\n"
        f"Issue [{finding.get('kind')}/{finding.get('code')}]{where}: "
        f"{finding.get('message')}\n\n"
        "Rewrite the ENTIRE file with the smallest change that resolves the issue. "
        "Preserve all existing behavior, style and imports. Do not add commentary. "
        "Return the whole file inside a single fenced code block.\n\n"
        f"```\n{content}\n```"
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def extract_file(output: str) -> str | None:
    """Pull the corrected file out of the model output.

    Prefers the largest fenced code block; falls back to the raw output if the
    model returned bare code. Returns None if nothing usable is found.
    """

    blocks = _FENCE_RE.findall(output or "")
    if blocks:
        best = max(blocks, key=len)
        return best.rstrip("\n") + "\n"
    stripped = (output or "").strip()
    return (stripped + "\n") if stripped else None


def make_diff(path: str, before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def validate_syntax(path: str, content: str) -> tuple[bool, str]:
    """For Python files, the rewrite must still parse; other types pass through."""

    if not path.endswith(".py"):
        return True, "non-python: syntax check skipped"
    try:
        ast.parse(content)
    except SyntaxError as exc:
        return False, f"python syntax error: {exc}"
    return True, "python parses"


# --- model selection + completion -------------------------------------------


async def select_coder_model(session: AsyncSession) -> str | None:
    """The configured coder model if usable, else an available coder-looking one."""

    configured = get_settings().code_patch_model.strip()
    if configured:
        return configured
    rows = (await session.execute(select(LLMModel).where(LLMModel.available.is_(True)))).scalars()
    for m in rows:
        if m.name and m.name != ECHO_MODEL and is_coder_model(m.name):
            return m.name
    return None


async def complete(model: str, messages: list[ChatMessage]) -> str:
    """One-shot completion from a real model. Refuses the echo stub (no faking)."""

    decision = await router.select(requested_model=model)
    if decision.provider.name == "echo":
        raise CodePatchError(
            f"coder model '{model}' is not being served (got the echo stub); "
            "download a code-capable model on a node first"
        )
    acc: list[str] = []
    async for piece in decision.provider.stream_chat(messages, decision.model):
        acc.append(piece)
    return "".join(acc)


# --- entry point ------------------------------------------------------------


async def propose_patch(session: AsyncSession, issue: MaintenanceIssue) -> MaintenanceRun:
    """Have a coder model write the fix, validate it, and open an approval gate."""

    sample = issue.sample or {}
    rel = str(sample.get("path") or "")
    if not rel:
        raise CodePatchError("issue has no file path to patch")

    root = code_review_service.repo_root()
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise CodePatchError(f"file not found in repo: {rel}")
    content = target.read_text(encoding="utf-8", errors="replace")
    if len(content.encode("utf-8")) > get_settings().code_patch_max_file_bytes:
        raise CodePatchError("file too large to patch safely")

    model = await select_coder_model(session)
    if not model:
        raise CodePatchError(
            "no code-capable model available — configure ATLAS_CODE_PATCH_MODEL or "
            "download a coder model (e.g. a *-coder) on a node"
        )

    output = await complete(model, build_messages(rel, content, sample))
    new_content = extract_file(output)
    if not new_content or new_content.strip() == content.strip():
        raise CodePatchError("model returned no usable change")
    ok, why = validate_syntax(rel, new_content)
    if not ok:
        raise CodePatchError(f"rejected: {why}")

    patch = make_diff(rel, content, new_content)
    logger.info(
        "code patch synthesized",
        extra={
            "event": "code_patch",
            "context": {"issue_id": issue.id, "path": rel, "model": model},
        },
    )
    run, _approval = await maintenance_service.create_fix(
        session, issue, files={rel: content}, patch=patch
    )
    return run
