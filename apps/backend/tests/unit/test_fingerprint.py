"""Unit tests for log fingerprinting (spec §11 step 2)."""

from __future__ import annotations

from app.maintenance.fingerprint import compute_fingerprint, normalize_message


def test_normalize_strips_volatile_parts():
    a = normalize_message("Timeout after 1234 ms on request 0xdeadbeef")
    b = normalize_message("Timeout after 55 ms on request 0xcafebabe")
    assert a == b


def test_same_error_different_values_same_fingerprint():
    fp1 = compute_fingerprint(service="backend", message="ollama_timeout after 30s", level="ERROR")
    fp2 = compute_fingerprint(service="backend", message="ollama_timeout after 5s", level="ERROR")
    assert fp1 == fp2


def test_different_errors_differ():
    fp1 = compute_fingerprint(service="backend", message="db connection refused", level="ERROR")
    fp2 = compute_fingerprint(service="backend", message="redis connection refused", level="ERROR")
    assert fp1 != fp2


def test_service_scopes_fingerprint():
    fp1 = compute_fingerprint(service="backend", message="boom")
    fp2 = compute_fingerprint(service="frontend", message="boom")
    assert fp1 != fp2
