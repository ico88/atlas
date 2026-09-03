"""Unit tests for the real self-healing sandbox (ROADMAP PR 17)."""

from __future__ import annotations

import difflib

from app.maintenance.sandbox import run_sandbox


def _patch(fname: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{fname}",
            tofile=f"b/{fname}",
        )
    )


def test_apply_only_check_passes_for_clean_patch():
    before = "a\nb\nc\n"
    after = "a\nB\nc\n"
    patch = _patch("f.txt", before, after)
    res = run_sandbox({"f.txt": before}, patch)
    assert res.applied is True
    assert res.passed is True
    assert res.command is None
    assert res.files == ["f.txt"]


def test_patch_that_does_not_apply_is_reported_not_raised():
    # Seed content differs from what the patch expects -> rejected cleanly.
    patch = _patch("f.txt", "one\ntwo\nthree\n", "one\nTWO\nthree\n")
    res = run_sandbox({"f.txt": "totally\ndifferent\n"}, patch)
    assert res.applied is False
    assert res.passed is False
    assert "patch rejected" in res.summary


def test_check_command_success():
    before = "x\n"
    after = "y\n"
    patch = _patch("f.txt", before, after)
    res = run_sandbox(
        {"f.txt": before}, patch, check_command='sh -c "test -f f.txt"'
    )
    assert res.applied is True
    assert res.passed is True
    assert res.returncode == 0


def test_check_command_failure_is_captured():
    before = "x\n"
    after = "y\n"
    patch = _patch("f.txt", before, after)
    res = run_sandbox({"f.txt": before}, patch, check_command='sh -c "exit 3"')
    assert res.applied is True
    assert res.passed is False
    assert res.returncode == 3
    assert "failed" in res.summary


def test_seed_path_traversal_is_blocked():
    before = "x\n"
    patch = _patch("f.txt", before, "y\n")
    res = run_sandbox({"../escape.txt": "nope"}, patch)
    # A traversal seed aborts before applying -> reported, never written outside.
    assert res.applied is False
    assert res.passed is False
