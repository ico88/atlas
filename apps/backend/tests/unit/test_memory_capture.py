"""Unit tests for automatic memory capture (ROADMAP PR 14 auto-capture)."""

from __future__ import annotations

from app.rag.memory_capture import extract_facts


def test_captures_name_italian():
    assert "The user's name is Federico" in extract_facts("ciao, sono Federico")
    assert "The user's name is Federico" in extract_facts("mi chiamo Federico!")


def test_captures_name_english():
    assert "The user's name is Alice" in extract_facts("hi, my name is Alice")
    assert "The user's name is Bob" in extract_facts("I am Bob")


def test_ignores_non_name_after_sono():
    # "sono stanco" is not a name (lowercase / stop word).
    assert extract_facts("sono stanco oggi") == []
    assert extract_facts("i am tired") == []


def test_captures_remember_clause():
    facts = extract_facts("ricorda che il meeting è alle 15")
    assert any("meeting" in f for f in facts)


def test_captures_preference_and_attribute():
    assert any("prefers" in f for f in extract_facts("preferisco il tè verde"))
    attr = extract_facts("il mio colore preferito è blu")
    assert any("blu" in f for f in attr)


def test_empty_and_dedup():
    assert extract_facts("") == []
    facts = extract_facts("sono Federico. sono Federico")
    assert facts.count("The user's name is Federico") == 1
