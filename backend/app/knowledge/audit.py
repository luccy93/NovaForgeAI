from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.knowledge.models import KnowledgeQuery

log = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 2048

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_HEX_TOKEN_RE = re.compile(r"\b[a-fA-F0-9]{32,}\b")


def _sanitize_query(text: str) -> str:
    """Mask PII patterns in query text. Email -> [email], SSN -> [ssn], card -> [card], token -> [token]."""
    if not text:
        return ""

    sanitized = text
    try:
        sanitized = _EMAIL_RE.sub("[email]", sanitized)
        sanitized = _SSN_RE.sub("[ssn]", sanitized)
        sanitized = _CARD_RE.sub("[card]", sanitized)
        sanitized = _HEX_TOKEN_RE.sub("[token]", sanitized)
    except Exception:
        pass

    if len(sanitized) > MAX_QUERY_LENGTH:
        sanitized = sanitized[:MAX_QUERY_LENGTH]

    return sanitized


async def audit_query(
    db,
    tenant,
    query_text,
    query_type,
    filters,
    results_count,
    latency_ms,
    *,
    user_id=None,
    session_id=None,
    classification="INTERNAL",
    metadata=None,
) -> str:
    """Create a KnowledgeQuery record. Returns query_id. Sanitizes query_text and never logs raw API keys."""
    try:
        sanitized_text = _sanitize_query(str(query_text) if query_text else "")

        sanitized_filters = {}
        if filters:
            try:
                for k, v in filters.items():
                    kl = str(k).lower()
                    if any(term in kl for term in ("key", "token", "secret", "password", "auth")):
                        continue
                    sanitized_filters[k] = v
            except Exception:
                sanitized_filters = {}

        record = KnowledgeQuery(
            tenant=tenant,
            query_text=sanitized_text,
            query_type=query_type,
            filters=sanitized_filters,
            results_count=results_count,
            latency_ms=latency_ms,
            user_id=user_id,
            session_id=session_id,
            classification=classification,
            metadata_=metadata or {},
        )
        db.add(record)
        await db.flush()
        return str(record.id)
    except Exception:
        log.warning("Failed to audit query for tenant %s", tenant, exc_info=True)
        return ""


async def usage_stats(db, tenant, *, since_hours: int = 24) -> dict:
    """Return usage stats: total_queries, by_type, avg_latency_ms, unique_users, top_terms."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        stmt = (
            select(KnowledgeQuery).where(
                KnowledgeQuery.tenant == tenant,
                KnowledgeQuery.created_at >= cutoff,
            )
        )
        rows = (await db.execute(stmt)).scalars().all()

        if not rows:
            return {
                "total_queries": 0,
                "by_type": {},
                "avg_latency_ms": 0.0,
                "unique_users": 0,
                "top_terms": [],
            }

        total = len(rows)
        by_type: dict[str, int] = {}
        total_latency = 0.0
        latency_count = 0
        unique_users: set[str] = set()
        term_freq: dict[str, int] = {}

        for q in rows:
            qt = q.query_type or "unknown"
            by_type[qt] = by_type.get(qt, 0) + 1

            lat = q.latency_ms
            if lat is not None:
                try:
                    total_latency += float(lat)
                    latency_count += 1
                except (TypeError, ValueError):
                    pass

            uid = q.user_id
            if uid:
                unique_users.add(str(uid))

            text = q.query_text or ""
            if text:
                for token in text.split():
                    cleaned = re.sub(r"[^a-zA-Z0-9]", "", token.lower())
                    if len(cleaned) > 2:
                        term_freq[cleaned] = term_freq.get(cleaned, 0) + 1

        top_terms = sorted(term_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        avg_latency = round(total_latency / latency_count, 2) if latency_count else 0.0

        return {
            "total_queries": total,
            "by_type": by_type,
            "avg_latency_ms": avg_latency,
            "unique_users": len(unique_users),
            "top_terms": [t[0] for t in top_terms],
        }
    except Exception:
        log.warning("Failed to get usage stats for tenant %s", tenant, exc_info=True)
        return {
            "total_queries": 0,
            "by_type": {},
            "avg_latency_ms": 0.0,
            "unique_users": 0,
            "top_terms": [],
        }


async def get_query_history(db, tenant, *, user_id=None, limit: int = 50) -> list[dict]:
    """Return recent queries for a tenant/user."""
    try:
        conditions = [KnowledgeQuery.tenant == tenant]
        if user_id:
            conditions.append(KnowledgeQuery.user_id == user_id)

        stmt = (
            select(KnowledgeQuery)
            .where(*conditions)
            .order_by(KnowledgeQuery.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        rows = (await db.execute(stmt)).scalars().all()

        history: list[dict] = []
        for q in rows:
            history.append({
                "query_id": str(q.id),
                "query_text": q.query_text,
                "query_type": q.query_type,
                "results_count": q.results_count,
                "latency_ms": q.latency_ms,
                "user_id": q.user_id,
                "classification": q.classification,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            })

        return history
    except Exception:
        log.warning("Failed to get query history for tenant %s", tenant, exc_info=True)
        return []
