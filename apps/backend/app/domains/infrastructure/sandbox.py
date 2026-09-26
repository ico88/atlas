"""Real, isolated validation sandbox for the Maintenance Agent (ROADMAP PR 17).

This turns the maintenance loop's "tests" step from a placeholder string into an
actual execution: a proposed unified-diff *patch* is applied to a throwaway copy
of the affected files and an operator-configured *check command* is run against
it, capturing the real exit status and output.

Safety by construction:

* Everything happens in a fresh temporary directory that is deleted afterwards —
  the real repository is never touched, so a bad patch can only break the
  sandbox, never the running system.
* The patch is applied with ``git apply`` in *check* mode first; a patch that
  does not apply cleanly fails fast and is reported, never force-applied.
* The check command comes only from server configuration
  (``ATLAS_MAINTENANCE_CHECK_COMMAND``), never from an API request, so this is
  not a remote-code-execution surface. When it is empty the sandbox performs an
  apply-only check (the patch must apply cleanly), which is still a real result.

The functions are pure w.r.t. the database (they take plain data), so they are
unit-testable without a model or a live repo.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Never let captured output blow up the DB row / response.
_MAX_OUTPUT = 4000


class SandboxError(RuntimeError):
    """Raised when the sandbox cannot be prepared or a patch cannot be applied."""


@dataclass
class SandboxResult:
    """Outcome of a real sandbox run (patch application + optional check)."""

    applied: bool
    passed: bool
    returncode: int | None
    command: str | None
    stdout: str
    stderr: str
    summary: str
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "passed": self.passed,
            "returncode": self.returncode,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "summary": self.summary,
            "files": self.files,
        }


def _clip(text: str) -> str:
    text = text or ""
    if len(text) > _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + f"\n… (+{len(text) - _MAX_OUTPUT} bytes truncated)"
    return text


def _patched_files(patch: str) -> list[str]:
    """Best-effort list of files a unified diff touches (for the audit trail)."""

    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            path = line[4:].strip()
            if path.startswith(("a/", "b/")):
                path = path[2:]
            if path and path not in files:
                files.append(path)
    return files


def _write_seed(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        # Contain everything under ``root`` — reject path traversal outright.
        target = (root / rel).resolve()
        if not str(target).startswith(str(root.resolve())):
            raise SandboxError(f"unsafe seed path: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def apply_patch(root: Path, patch: str) -> list[str]:
    """Apply a unified-diff ``patch`` inside ``root``. Return the touched files.

    Uses ``git apply`` (available wherever the repo is), checking first so a
    patch that does not apply cleanly is rejected rather than partially applied.
    """

    if shutil.which("git") is None:  # pragma: no cover - git present in CI/dev
        raise SandboxError("git is not available to apply the patch")
    if not patch.strip():
        raise SandboxError("empty patch")

    patch_file = root / ".atlas-fix.patch"
    patch_file.write_text(patch if patch.endswith("\n") else patch + "\n", encoding="utf-8")

    base = ["git", "apply", "--whitespace=nowarn"]
    check = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [*base, "--check", str(patch_file)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        raise SandboxError(f"patch does not apply: {check.stderr.strip() or 'unknown error'}")

    applied = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [*base, str(patch_file)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if applied.returncode != 0:
        raise SandboxError(f"patch failed to apply: {applied.stderr.strip()}")

    patch_file.unlink(missing_ok=True)
    return _patched_files(patch)


def run_check(root: Path, command: str, timeout: float) -> tuple[int, str, str]:
    """Run a validation ``command`` (server-configured) inside ``root``."""

    argv = shlex.split(command)
    if not argv:
        return 0, "", ""
    try:
        proc = subprocess.run(  # noqa: S603 - argv from operator config, not a request
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SandboxError(f"check command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"check command timed out after {timeout:.0f}s") from exc
    return proc.returncode, proc.stdout, proc.stderr


def run_sandbox(
    files: dict[str, str],
    patch: str,
    *,
    check_command: str | None = None,
    timeout: float = 120.0,
) -> SandboxResult:
    """Apply ``patch`` to ``files`` in an isolated temp dir and run ``check_command``.

    Returns a structured :class:`SandboxResult`; never raises for an ordinary
    "patch didn't apply" or "tests failed" outcome (those are reported as a
    non-passing result), only for genuine infrastructure problems.
    """

    tmp = Path(tempfile.mkdtemp(prefix="atlas-sandbox-"))
    try:
        try:
            _write_seed(tmp, files)
            touched = apply_patch(tmp, patch)
        except SandboxError as exc:
            return SandboxResult(
                applied=False,
                passed=False,
                returncode=None,
                command=None,
                stdout="",
                stderr=str(exc),
                summary=f"patch rejected: {exc}",
                files=_patched_files(patch),
            )

        command = (check_command or "").strip()
        if not command:
            return SandboxResult(
                applied=True,
                passed=True,
                returncode=0,
                command=None,
                stdout="",
                stderr="",
                summary=f"patch applies cleanly to {len(touched)} file(s) (apply-only check)",
                files=touched,
            )

        try:
            code, out, err = run_check(tmp, command, timeout)
        except SandboxError as exc:
            return SandboxResult(
                applied=True,
                passed=False,
                returncode=None,
                command=command,
                stdout="",
                stderr=str(exc),
                summary=f"check could not run: {exc}",
                files=touched,
            )

        passed = code == 0
        summary = (
            f"patch applied; `{command}` "
            + ("passed" if passed else f"failed (exit {code})")
            + f" on {len(touched)} file(s)"
        )
        return SandboxResult(
            applied=True,
            passed=passed,
            returncode=code,
            command=command,
            stdout=_clip(out),
            stderr=_clip(err),
            summary=summary,
            files=touched,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
