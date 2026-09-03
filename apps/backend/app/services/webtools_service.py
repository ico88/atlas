"""Web tools orchestration (ROADMAP PR 15): search → fetch → rank → cite.

Ties the pieces together behind a small API. Off unless
``ATLAS_WEB_TOOLS_ENABLED`` is true. Everything is policy-guarded and returns
citations (title + url + score) so answers built on web content are attributable.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from app.core.config import Settings
from app.services import settings_service
from app.webtools import policy as pol
from app.webtools import search as search_mod
from app.webtools.extract import snippet
from app.webtools.fetch import FetchResult, fetch_url
from app.webtools.ranking import rank

logger = logging.getLogger(__name__)


class WebToolsDisabled(RuntimeError):
    """Raised when web tools are called but disabled in configuration."""


@dataclass
class Citation:
    title: str
    url: str
    snippet: str
    score: float


def build_policy(settings: Settings) -> pol.UrlPolicy:
    return pol.UrlPolicy(
        allow_private_ips=settings.web_allow_private_ips,
        allowlist=tuple(settings.web_allowlist),
        denylist=tuple(settings.web_denylist),
        max_bytes=settings.web_fetch_max_bytes,
        timeout=settings.web_fetch_timeout,
    )


def _ensure_enabled(settings: Settings) -> None:
    if not settings.web_tools_enabled:
        raise WebToolsDisabled("web tools are disabled (set ATLAS_WEB_TOOLS_ENABLED=true)")


async def fetch(url: str, settings: Settings | None = None) -> FetchResult:
    """Safely fetch a single URL (policy-guarded)."""

    settings = settings or await settings_service.get_effective_settings()
    _ensure_enabled(settings)
    return await fetch_url(
        url, build_policy(settings), user_agent=settings.web_user_agent
    )


async def search(
    query: str,
    *,
    limit: int | None = None,
    fetch_bodies: bool = True,
    settings: Settings | None = None,
) -> dict[str, object]:
    """Search, optionally fetch the top candidates, rank them, and return citations."""

    settings = settings or await settings_service.get_effective_settings()
    _ensure_enabled(settings)
    limit = limit or settings.web_max_results

    provider = search_mod.get_provider(
        settings.web_search_provider,
        url=settings.web_search_url,
        timeout=settings.web_fetch_timeout,
        user_agent=settings.web_user_agent,
    )
    candidates = await provider.search(query, limit=limit)

    policy = build_policy(settings)
    docs: list[str] = []
    enriched: list[dict[str, object]] = []
    for cand in candidates:
        body_text = cand.snippet
        fetched = False
        if fetch_bodies:
            try:
                result = await fetch_url(cand.url, policy, user_agent=settings.web_user_agent)
                body_text = result.text or cand.snippet
                fetched = True
            except pol.PolicyError as exc:
                logger.info("skipping candidate %s: %s", cand.url, exc)
            except Exception as exc:  # noqa: BLE001 - one bad result must not fail search
                logger.warning("fetch failed for %s: %s", cand.url, exc)
        enriched.append(
            {"title": cand.title, "url": cand.url, "text": body_text, "fetched": fetched}
        )
        docs.append(f"{cand.title}\n{body_text}")

    ranked = rank(query, docs)
    citations: list[Citation] = []
    for scored in ranked:
        item = enriched[scored.index]
        citations.append(
            Citation(
                title=str(item["title"]),
                url=str(item["url"]),
                snippet=snippet(str(item["text"]), query),
                score=scored.score,
            )
        )

    return {
        "query": query,
        "provider": provider.name,
        "count": len(citations),
        "citations": [asdict(c) for c in citations],
    }
