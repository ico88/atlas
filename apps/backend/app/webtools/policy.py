"""URL policy and SSRF guard for web tools (ROADMAP PR 15).

Pure, dependency-light functions so they are unit-testable without the network:

- ``normalize_url``    reject anything but http/https, require a host.
- ``host_matches``     suffix match for allow/deny lists.
- ``ip_is_private``    block loopback/private/link-local/reserved ranges.
- ``check_url``        policy decision on a URL *before* DNS resolution.
- ``check_resolved``   second check on the resolved IPs (DNS-rebinding guard).

The fetch layer resolves the host and calls ``check_resolved`` so a name that
passes ``check_url`` but resolves to a private address is still blocked.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class UrlPolicy:
    allow_private_ips: bool = False
    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()
    max_bytes: int = 2_000_000
    timeout: float = 10.0


class PolicyError(ValueError):
    """Raised when a URL is rejected by policy."""


def normalize_url(url: str) -> tuple[str, str]:
    """Return ``(scheme, host)`` for a valid http(s) URL or raise ``PolicyError``."""

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise PolicyError(f"scheme '{scheme or '(none)'}' not allowed (http/https only)")
    host = (parts.hostname or "").lower()
    if not host:
        raise PolicyError("URL has no host")
    return scheme, host


def host_matches(host: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """True if host equals or is a subdomain of any pattern (suffix match)."""

    host = host.lower().rstrip(".")
    for raw in patterns:
        pat = raw.lower().lstrip(".").rstrip(".")
        if not pat:
            continue
        if host == pat or host.endswith("." + pat):
            return True
    return False


def ip_is_private(value: str) -> bool:
    """True if the address is loopback/private/link-local/reserved/multicast."""

    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_url(url: str, policy: UrlPolicy) -> str:
    """Validate a URL against policy (pre-DNS). Returns the host or raises."""

    _scheme, host = normalize_url(url)

    if policy.denylist and host_matches(host, policy.denylist):
        raise PolicyError(f"host '{host}' is on the deny list")
    if policy.allowlist and not host_matches(host, policy.allowlist):
        raise PolicyError(f"host '{host}' is not on the allow list")

    # A literal IP in the URL is checked immediately (no DNS needed).
    if not policy.allow_private_ips and ip_is_private(host):
        raise PolicyError(f"host '{host}' resolves to a private/loopback address")
    return host


def check_resolved(host: str, addresses: list[str], policy: UrlPolicy) -> None:
    """Second-stage check on resolved IPs (blocks DNS rebinding)."""

    if policy.allow_private_ips:
        return
    for addr in addresses:
        if ip_is_private(addr):
            raise PolicyError(
                f"host '{host}' resolves to private address {addr} (blocked)"
            )


def describe(policy: UrlPolicy) -> dict[str, object]:
    """A safe, secret-free description of the active policy (for the API)."""

    return {
        "allow_private_ips": policy.allow_private_ips,
        "allowlist": list(policy.allowlist),
        "denylist": list(policy.denylist),
        "max_bytes": policy.max_bytes,
        "timeout": policy.timeout,
    }
