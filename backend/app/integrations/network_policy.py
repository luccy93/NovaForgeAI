"""Outbound network policy — Volume 70 Commit 1.

Mandatory SSRF and egress protection for every external call made by
the integration platform. Fail-closed: unresolvable hosts, literal
private/loopback/link-local addresses, cloud metadata endpoints,
non-HTTP(S) schemes, embedded credentials and off-allowlist
destinations are all rejected.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.integrations.common import NetworkPolicyError

ALLOWED_SCHEMES = ("http", "https")
BLOCKED_SCHEMES = ("file", "ftp", "gopher", "dict", "ldap", "smb", "data", "javascript", "vbscript")

# Cloud metadata endpoints (all clouds converge on link-local, plus hostnames).
METADATA_HOSTS = (
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
)

MAX_REDIRECTS = 3


def _strip_brackets(host: str) -> str:
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def check_literal_host(host: str) -> None:
    """Reject literal IPs that are not globally routable."""
    host = _strip_brackets(host)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # not a literal; DNS path handles it
    if _is_blocked_ip(ip):
        raise NetworkPolicyError(f"blocked IP literal: {host}")


def check_resolved_host(host: str) -> None:
    """Resolve DNS and require every answer to be globally routable.

    Fail-closed on resolution failure; mitigates naive DNS rebinding by
    checking all returned addresses (callers re-check per redirect hop).
    """
    host = _strip_brackets(host)
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise NetworkPolicyError(f"DNS resolution failed for {host}: {exc}") from exc
    if not infos:
        raise NetworkPolicyError(f"no DNS answers for {host}")
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            raise NetworkPolicyError(f"unparsable DNS answer for {host}")
        if _is_blocked_ip(ip):
            raise NetworkPolicyError(f"DNS for {host} resolves to blocked address")


def validate_url(url: str, *, allowlist: list[str] | None = None) -> str:
    """Validate an outbound URL. Returns the URL unchanged or raises."""
    if not url or not isinstance(url, str) or len(url) > 2048:
        raise NetworkPolicyError("URL required (max 2048 chars)")
    try:
        parsed = urlparse(url.strip())
    except Exception as exc:
        raise NetworkPolicyError(f"malformed URL: {exc}") from exc
    scheme = (parsed.scheme or "").lower()
    if scheme in BLOCKED_SCHEMES or scheme not in ALLOWED_SCHEMES:
        raise NetworkPolicyError(f"blocked URL scheme: {scheme or '(none)'}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise NetworkPolicyError("URL must have a host")
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise NetworkPolicyError("credentials in URL are not allowed")
    if host in METADATA_HOSTS or host.endswith(".metadata.google.internal"):
        raise NetworkPolicyError(f"blocked metadata host: {host}")
    check_literal_host(host)
    check_resolved_host(host)
    if allowlist:
        allowed = any(host == entry.lower() or host.endswith("." + entry.lower()) for entry in allowlist)
        if not allowed:
            raise NetworkPolicyError(f"host not in destination allowlist: {host}")
    return url


def scrub(url: str) -> str:
    """Render a URL safe for logs: host only, no query/userinfo."""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.hostname or '?'}:{parsed.port or ''}".rstrip(":")
    except Exception:
        return "?"
