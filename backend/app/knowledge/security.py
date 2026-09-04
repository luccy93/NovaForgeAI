"""Knowledge security hardening — Volume 68.

Provides input validation, PII detection/redaction, in-memory rate
limiting, connector config sanitization, and security audit logging.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.knowledge.common import MAX_QUERY_LENGTH, emit_event

logger = logging.getLogger(__name__)

# Injection patterns
_SQL_INJECTION_RE = re.compile(
    r"(?:;\s*(?:DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC)\s|--(?:\s|$)|/\*|\*/|'\s*OR\s*')",
    re.IGNORECASE,
)
_XSS_RE = re.compile(r"<script[^>]*>|javascript:|on\w+\s*=", re.IGNORECASE)
_PATH_TRAVERSAL_RE = re.compile(r"\.\.\/|\.\.\\|%2e%2e|%252e%252e", re.IGNORECASE)

# PII patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_HEX_TOKEN_RE = re.compile(r"\b[a-fA-F0-9]{32,}\b")

# Rate limiting state (in-memory, per-process)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # seconds


def validate_query_input(query: str) -> dict:
    """Validate and sanitize a search query.
    
    Returns: {"valid": bool, "cleaned_query": str, "violations": list[str]}
    """
    violations: list[str] = []
    
    if not query or not query.strip():
        return {"valid": False, "cleaned_query": "", "violations": ["empty_query"]}
    
    cleaned = query.strip()
    
    if len(cleaned) > MAX_QUERY_LENGTH:
        cleaned = cleaned[:MAX_QUERY_LENGTH]
        violations.append("query_truncated")
    
    if _SQL_INJECTION_RE.search(cleaned):
        violations.append("sql_injection_suspected")
        cleaned = _SQL_INJECTION_RE.sub("", cleaned)
    
    if _XSS_RE.search(cleaned):
        violations.append("xss_suspected")
        cleaned = _XSS_RE.sub("", cleaned)
    
    if _PATH_TRAVERSAL_RE.search(cleaned):
        violations.append("path_traversal_suspected")
        cleaned = _PATH_TRAVERSAL_RE.sub("", cleaned)
    
    if len(cleaned.encode("utf-8")) > 10_000:
        violations.append("oversized_query")
        cleaned = cleaned[:3000]
    
    return {
        "valid": len(violations) == 0 or cleaned.strip() != "",
        "cleaned_query": cleaned.strip(),
        "violations": violations,
    }


def redact_pii(text: str) -> str:
    """Detect and redact PII from text.
    
    Replaces emails, phone numbers, SSNs, credit cards, and hex tokens.
    """
    if not text:
        return text
    
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = _SSN_RE.sub("[REDACTED_SSN]", redacted)
    redacted = _CARD_RE.sub("[REDACTED_CARD]", redacted)
    redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    redacted = _HEX_TOKEN_RE.sub("[REDACTED_TOKEN]", redacted)
    
    return redacted


def check_rate_limit(
    tenant: str,
    user_id: str,
    action: str,
    *,
    max_requests: int = 100,
    window_seconds: int = 60,
) -> dict:
    """In-memory sliding-window rate limiter.
    
    Returns: {"allowed": bool, "remaining": int, "retry_after_seconds": float}
    """
    try:
        now = time.monotonic()
        key = f"{tenant}:{user_id}:{action}"
        
        # Cleanup old entries periodically
        cutoff = now - _RATE_LIMIT_CLEANUP_INTERVAL
        if _rate_limit_store and len(_rate_limit_store[key]) > max_requests * 2:
            _rate_limit_store[key] = [
                t for t in _rate_limit_store[key] if t > cutoff
            ]
        
        # Sliding window
        window_start = now - window_seconds
        _rate_limit_store[key] = [t for t in _rate_limit_store[key] if t > window_start]
        
        current_count = len(_rate_limit_store[key])
        
        if current_count >= max_requests:
            oldest = _rate_limit_store[key][0] if _rate_limit_store[key] else now
            retry_after = window_seconds - (now - oldest)
            return {
                "allowed": False,
                "remaining": 0,
                "retry_after_seconds": max(retry_after, 0.1),
            }
        
        _rate_limit_store[key].append(now)
        
        return {
            "allowed": True,
            "remaining": max_requests - current_count - 1,
            "retry_after_seconds": 0.0,
        }
    except Exception as exc:
        # Fail-open: allow on error
        logger.warning("check_rate_limit failed: %s", exc)
        return {"allowed": True, "remaining": max_requests, "retry_after_seconds": 0.0}


def sanitize_connector_config(config: dict, source_type: str) -> dict:
    """Validate and sanitize a connector configuration.
    
    Strips dangerous fields, validates required fields per source type.
    """
    if not config:
        return {}
    
    # Always strip secrets/credentials
    sanitized = {}
    dangerous_keys = {"password", "secret", "token", "api_key", "private_key", "auth_token", "credentials"}
    
    for k, v in config.items():
        if k.lower() in dangerous_keys:
            sanitized[k] = "[REDACTED]" if isinstance(v, str) else v
        else:
            sanitized[k] = v
    
    # Type-specific validation
    required_fields: dict[str, list[str]] = {
        "code_intel": ["repository_url"],
        "data_catalog": ["catalog_url"],
        "conversations": ["channel_id"],
        "external": ["url"],
        "workflows": [],
        "incidents": [],
        "security": [],
    }
    
    for field in required_fields.get(source_type, []):
        if field not in sanitized or not sanitized[field]:
            logger.warning("Missing required field '%s' for source type '%s'", field, source_type)
    
    return sanitized


async def audit_sensitive_access(
    db: Any,
    tenant: str,
    user_id: str,
    resource: str,
    action: str,
    *,
    metadata: Optional[dict] = None,
) -> None:
    """Log a security-relevant access event for audit trail."""
    try:
        await emit_event("knowledge.security.sensitive_access", {
            "user_id": user_id,
            "resource": resource,
            "action": action,
            "metadata": metadata or {},
        }, tenant=tenant, source="knowledge")
    except Exception:
        pass


def detect_sensitive_query(query: str) -> dict:
    """Detect if a query targets sensitive content.
    
    Returns: {"is_sensitive": bool, "reasons": list[str]}
    """
    reasons: list[str] = []
    lower = query.lower()
    
    sensitive_terms = [
        "password", "secret", "credential", "private_key", "api_key",
        "token", "ssn", "social security", "credit card", "bank account",
    ]
    
    for term in sensitive_terms:
        if term in lower:
            reasons.append(f"contains_{term.replace(' ', '_')}")
    
    return {
        "is_sensitive": len(reasons) > 0,
        "reasons": reasons,
    }
