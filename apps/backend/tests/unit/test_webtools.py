"""Unit tests for web tools (ROADMAP PR 15): policy, extraction, ranking, search."""

from __future__ import annotations

import pytest
from app.webtools import policy as pol
from app.webtools.extract import extract_html, snippet
from app.webtools.ranking import rank, tokenize
from app.webtools.search import _parse_searxng


# --------------------------------------------------------------------------- #
# policy / SSRF guard
# --------------------------------------------------------------------------- #
def test_normalize_url_rejects_non_http():
    for bad in ("file:///etc/passwd", "ftp://host/x", "gopher://h", "javascript:alert(1)"):
        with pytest.raises(pol.PolicyError):
            pol.normalize_url(bad)


def test_normalize_url_requires_host():
    with pytest.raises(pol.PolicyError):
        pol.normalize_url("http:///nohost")


@pytest.mark.parametrize(
    "addr",
    ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0"],
)
def test_ip_is_private_blocks_internal(addr):
    assert pol.ip_is_private(addr) is True


@pytest.mark.parametrize("addr", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
def test_ip_is_public_allows_external(addr):
    assert pol.ip_is_private(addr) is False


def test_check_url_blocks_literal_private_ip():
    policy = pol.UrlPolicy()
    with pytest.raises(pol.PolicyError):
        pol.check_url("http://169.254.169.254/latest/meta-data/", policy)


def test_check_url_allows_private_when_opted_in():
    policy = pol.UrlPolicy(allow_private_ips=True)
    assert pol.check_url("http://127.0.0.1:8080/", policy) == "127.0.0.1"


def test_denylist_blocks_subdomains():
    policy = pol.UrlPolicy(denylist=("evil.com",))
    with pytest.raises(pol.PolicyError):
        pol.check_url("https://api.evil.com/x", policy)


def test_allowlist_rejects_outside_hosts():
    policy = pol.UrlPolicy(allowlist=("example.com",))
    assert pol.check_url("https://docs.example.com/x", policy) == "docs.example.com"
    with pytest.raises(pol.PolicyError):
        pol.check_url("https://other.org/x", policy)


def test_check_resolved_blocks_dns_rebinding():
    policy = pol.UrlPolicy()
    with pytest.raises(pol.PolicyError):
        pol.check_resolved("sneaky.example", ["93.184.216.34", "127.0.0.1"], policy)


def test_host_matches_suffix():
    assert pol.host_matches("a.b.example.com", ["example.com"]) is True
    assert pol.host_matches("notexample.com", ["example.com"]) is False


# --------------------------------------------------------------------------- #
# HTML extraction
# --------------------------------------------------------------------------- #
def test_extract_html_title_and_text_drops_scripts():
    html = """
    <html><head><title>  Hello  World </title><style>.x{color:red}</style></head>
    <body><script>var x=1;evil()</script><h1>Heading</h1><p>First para.</p>
    <p>Second &amp; para.</p></body></html>
    """
    title, text = extract_html(html)
    assert title == "Hello World"
    assert "Heading" in text
    assert "First para." in text
    assert "Second & para." in text
    assert "evil()" not in text
    assert "color:red" not in text


def test_extract_html_tolerates_malformed():
    title, text = extract_html("<p>unclosed <b>bold")
    assert "unclosed" in text
    assert title == ""


def test_snippet_centres_on_query_term():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    out = snippet(text, "delta", length=20)
    assert "delta" in out


# --------------------------------------------------------------------------- #
# ranking
# --------------------------------------------------------------------------- #
def test_rank_orders_by_relevance():
    docs = [
        "cats and dogs are common pets",
        "quantum chromodynamics and gluons",
        "the best dog training tips for dogs",
    ]
    ranked = rank("dog training", docs)
    assert ranked[0].index == 2  # most 'dog'/'training' hits
    assert ranked[0].score >= ranked[-1].score


def test_rank_empty_query_is_neutral():
    ranked = rank("", ["a", "b"])
    assert [r.score for r in ranked] == [0.0, 0.0]


def test_tokenize_lowercases_and_splits():
    assert tokenize("Hello, WORLD-42!") == ["hello", "world", "42"]


# --------------------------------------------------------------------------- #
# search provider parsing
# --------------------------------------------------------------------------- #
def test_parse_searxng_extracts_results():
    payload = {
        "results": [
            {"title": "A", "url": "https://a.example/x", "content": "snippet a"},
            {"title": "", "url": "https://b.example/y", "content": "snippet b"},
            {"title": "C", "url": "", "content": "no url dropped"},
        ]
    }
    results = _parse_searxng(payload, limit=10)
    assert len(results) == 2
    assert results[0].title == "A"
    assert results[1].title == "https://b.example/y"  # falls back to url


def test_parse_searxng_respects_limit_and_bad_input():
    payload = {"results": [{"url": f"https://x{i}.example"} for i in range(10)]}
    assert len(_parse_searxng(payload, limit=3)) == 3
    assert _parse_searxng("garbage", limit=5) == []
