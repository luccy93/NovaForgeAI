from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from math import pow

from sqlalchemy import select, func, update

from app.knowledge.models import KnowledgeDocument

log = logging.getLogger(__name__)


def compute_freshness_score(
    created_at: datetime,
    updated_at: datetime | None = None,
    half_life_days: float = 30.0,
) -> float:
    """Exponential decay freshness from last update. Score = 2^(-age/half_life), clamped [0.0, 1.0]."""
    try:
        now = datetime.now(timezone.utc)

        if updated_at is None:
            updated_at = created_at

        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        reference = max(created_at, updated_at)
        age_days = (now - reference).total_seconds() / 86400.0

        if age_days < 0:
            return 1.0

        score = pow(2.0, -age_days / half_life_days)
        return max(0.0, min(1.0, score))
    except Exception:
        log.warning("Failed to compute freshness score, defaulting to 0.0", exc_info=True)
        return 0.0


async def update_document_freshness(db, tenant, document_id) -> float:
    """Recompute and persist freshness_score for a document. Returns the new score."""
    try:
        now = datetime.now(timezone.utc)
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant == tenant,
        )
        doc = (await db.execute(stmt)).scalar_one_or_none()
        if doc is None:
            return 0.0

        score = compute_freshness_score(doc.created_at, doc.updated_at)
        doc.freshness_score = score
        await db.flush()
        return score
    except Exception:
        log.warning("Failed to update freshness for document %s", document_id, exc_info=True)
        return 0.0


async def mark_stale(db, tenant, *, older_than_hours: int = 168) -> int:
    """Mark documents as stale (freshness < 0.1) by updating their freshness_score. Returns count updated."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        stmt = (
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant == tenant,
                KnowledgeDocument.freshness_score < 0.1,
                KnowledgeDocument.created_at < cutoff,
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
        count = 0
        for doc in rows:
            doc.freshness_score = 0.0
            count += 1
        if count:
            await db.flush()
        return count
    except Exception:
        log.warning("Failed to mark stale documents for tenant %s", tenant, exc_info=True)
        return 0


async def get_freshness_stats(db, tenant) -> dict:
    """Return {"total": N, "fresh": N, "aging": N, "stale": N} based on score thresholds."""
    try:
        stmt = select(KnowledgeDocument.freshness_score).where(
            KnowledgeDocument.tenant == tenant,
        )
        rows = (await db.execute(stmt)).scalars().all()

        total = len(rows)
        fresh = 0
        aging = 0
        stale = 0

        for score in rows:
            s = float(score) if score is not None else 0.0
            if s >= 0.7:
                fresh += 1
            elif s >= 0.3:
                aging += 1
            else:
                stale += 1

        return {"total": total, "fresh": fresh, "aging": aging, "stale": stale}
    except Exception:
        log.warning("Failed to get freshness stats for tenant %s", tenant, exc_info=True)
        return {"total": 0, "fresh": 0, "aging": 0, "stale": 0}
