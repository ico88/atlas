"""Pluggable web search providers (ROADMAP PR 15).

The core never depends on a specific search engine. The default provider is
``NullSearchProvider`` (returns nothing) so the platform stays fully offline
until an operator configures a real one. ``SearxNGProvider`` queries a
self-hosted SearXNG JSON endpoint (operator-supplied, trusted config).

Result URLs are still passed through the fetch-layer policy before they are
fetched — the search provider only proposes candidates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        """Return up to ``limit`` candidate results (never raises)."""


class NullSearchProvider:
    """Offline default: no external search configured."""

    name = "none"

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:  # noqa: ARG002
        logger.info(
            "web search requested but no provider configured",
            extra={"event": "web_search_none"},
        )
        return []


class SearxNGProvider:
    """Query a self-hosted SearXNG instance via its JSON API."""

    name = "searxng"

    def __init__(
        self, url: str, *, timeout: float = 10.0, user_agent: str = "ATLAS-WebTools/1.0"
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._user_agent = user_agent

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        params = {"q": query, "format": "json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    self._url, params=params, headers={"User-Agent": self._user_agent}
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("searxng query failed: %s", exc, extra={"event": "web_search_error"})
            return []
        return _parse_searxng(data, limit)


def _parse_searxng(data: object, limit: int) -> list[SearchResult]:
    """Parse a SearXNG JSON payload into results (pure, testable)."""

    results: list[SearchResult] = []
    if not isinstance(data, dict):
        return results
    for item in data.get("results", [])[: max(0, limit)]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        results.append(
            SearchResult(
                title=str(item.get("title", "")).strip() or url,
                url=url,
                snippet=str(item.get("content", "")).strip(),
            )
        )
    return results


def get_provider(
    provider: str, *, url: str = "", timeout: float = 10.0, user_agent: str = "ATLAS-WebTools/1.0"
) -> SearchProvider:
    """Factory: build the configured search provider (defaults to offline)."""

    if provider == "searxng" and url:
        return SearxNGProvider(url, timeout=timeout, user_agent=user_agent)
    return NullSearchProvider()
