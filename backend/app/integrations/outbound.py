"""Governed outbound HTTP client — Volume 70 Commit 1.

The single mandatory path for external calls from the integration
platform: network-policy enforcement, per-tenant/endpoint rate limits,
bounded retries (existing sre resilience classifier), timeouts, response
size caps and redirect re-validation. Caller-supplied Authorization
headers are stripped — authentication comes only from managed
credentials injected by the execution layer. Bodies and query strings
are never logged.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.integrations.common import NetworkPolicyError, ValidationError
from app.integrations.network_policy import MAX_REDIRECTS, scrub, validate_url

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_REQUEST_BYTES = 512 * 1024
ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")


async def _check_rate_limit(scope_key: str, max_requests: int, window_seconds: int = 60) -> None:
    try:
        from app.core.redis import rate_limit_check
        allowed, _ = await rate_limit_check(scope_key, max_requests, window_seconds)
    except Exception:
        allowed = True
    if not allowed:
        raise ValidationError(f"rate limit exceeded for {scope_key}")


def _strip_auth(headers: dict) -> dict:
    return {k: v for k, v in (headers or {}).items() if k.lower() not in ("authorization", "proxy-authorization")}


async def execute(
    *,
    tenant: str,
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Optional[bytes] = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allowlist: Optional[list[str]] = None,
    rate_limit_key: Optional[str] = None,
    rate_limit_max: int = 100,
    rate_limit_window: int = 60,
    max_attempts: int = 3,
    actor: str = "",
    managed_auth: Optional[dict] = None,
) -> dict:
    """Execute one governed outbound request. Returns a result dict."""
    from app.sre.resilience import RetryPolicy, classify_retry, retry_async

    method = (method or "GET").upper()
    if method not in ALLOWED_METHODS:
        raise ValidationError(f"method not allowed: {method}")
    if body and len(body) > DEFAULT_MAX_REQUEST_BYTES:
        raise ValidationError("request body too large")
    if not (1.0 <= float(timeout) <= 120.0):
        raise ValidationError("timeout must be 1-120s")

    validate_url(url, allowlist=allowlist)
    scope = rate_limit_key or f"integrations:{tenant}:outbound"
    await _check_rate_limit(scope, rate_limit_max, rate_limit_window)

    clean_headers = _strip_auth(headers)
    if managed_auth and managed_auth.get("header") and managed_auth.get("value"):
        # Managed credentials only: injected after caller auth is stripped.
        clean_headers[str(managed_auth["header"])] = str(managed_auth["value"])
    policy = RetryPolicy(max_attempts=max(1, min(int(max_attempts), 5)),
                         base_delay_seconds=0.5, max_delay_seconds=8.0)

    async def _single_attempt(target_url: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=False) as client:
            return await client.request(method, target_url, headers=clean_headers, content=body)

    attempts = 0
    started = time.monotonic()
    current_url = url
    last_exc: Optional[Exception] = None
    for _ in range(MAX_REDIRECTS + 1):
        async def _do() -> httpx.Response:
            return await _single_attempt(current_url)

        try:
            response = await retry_async(_do, policy=policy, name="integrations.outbound")
        except Exception as exc:
            last_exc = exc
            raise
        attempts += 1
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if not location:
                raise NetworkPolicyError("redirect without location")
            if location.startswith("/"):
                from urllib.parse import urlparse
                base = urlparse(current_url)
                location = f"{base.scheme}://{base.netloc}{location}"
            validate_url(location, allowlist=allowlist)
            current_url = location
            continue
        content = response.content or b""
        if len(content) > max_response_bytes:
            raise ValidationError("response too large")
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info("outbound %s %s -> %d (%dms, tenant=%s)", method, scrub(current_url),
                    response.status_code, latency_ms, tenant)
        return {
            "status_code": response.status_code,
            "headers": {k: v for k, v in response.headers.items()
                        if k.lower() not in ("authorization", "set-cookie")},
            "body": content,
            "bytes": len(content),
            "latency_ms": latency_ms,
            "attempts": attempts,
            "url": scrub(current_url),
        }
    raise NetworkPolicyError("too many redirects")
