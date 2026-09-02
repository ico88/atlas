"""Safe HTTP fetch with SSRF, size and time guards (ROADMAP PR 15).

Flow for every fetch:
1. ``policy.check_url``     — scheme/host/allow-deny + literal-IP check.
2. resolve the host        — ``socket.getaddrinfo``.
3. ``policy.check_resolved`` — reject private resolved IPs (DNS-rebinding guard).
4. stream the body         — abort past ``max_bytes``; enforce a total timeout.

Returns a :class:`FetchResult` (text extracted from HTML). Never follows a
redirect to a disallowed host: redirects are resolved manually so each hop is
re-checked by policy.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

import httpx

from app.webtools import policy as pol
from app.webtools.extract import extract_html

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 4


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    title: str
    text: str
    truncated: bool
    bytes_read: int


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:  # DNS failure
        raise pol.PolicyError(f"could not resolve host '{host}': {exc}") from exc
    return sorted({info[4][0] for info in infos})


async def _read_capped(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    body = bytearray()
    truncated = False
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            truncated = True
            del body[max_bytes:]
            break
    return bytes(body), truncated


async def fetch_url(
    url: str,
    policy: pol.UrlPolicy,
    *,
    user_agent: str = "ATLAS-WebTools/1.0",
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """Fetch a URL safely and return extracted text. Raises ``PolicyError`` if blocked."""

    owns_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=False, timeout=policy.timeout)
    current = url
    try:
        for _hop in range(_MAX_REDIRECTS + 1):
            host = pol.check_url(current, policy)
            pol.check_resolved(host, _resolve(host), policy)
            request = client.build_request(
                "GET", current, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"}
            )
            response = await client.send(request, stream=True)
            try:
                if response.is_redirect and response.has_redirect_location:
                    current = str(response.next_request.url) if response.next_request else (
                        response.headers.get("location", "")
                    )
                    await response.aclose()
                    if not current:
                        raise pol.PolicyError("redirect without a location")
                    continue
                body, truncated = await _read_capped(response, policy.max_bytes)
            finally:
                await response.aclose()

            content_type = response.headers.get("content-type", "").split(";")[0].strip()
            decoded = body.decode(response.encoding or "utf-8", errors="replace")
            if "html" in content_type or (not content_type and "<html" in decoded[:2000].lower()):
                title, text = extract_html(decoded)
            else:
                title, text = "", decoded
            return FetchResult(
                url=url,
                final_url=str(response.url),
                status=response.status_code,
                content_type=content_type or "text/plain",
                title=title,
                text=text,
                truncated=truncated,
                bytes_read=len(body),
            )
        raise pol.PolicyError("too many redirects")
    finally:
        if owns_client:
            await client.aclose()
