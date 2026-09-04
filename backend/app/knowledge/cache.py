"""Semantic search result caching — Volume 68.

Provides content-addressed caching of search results with TTL expiry,
source-based invalidation, and cache hit/miss statistics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import emit_event
from app.knowledge.models import KnowledgeCacheEntry, KnowledgeDocument, KnowledgeSource

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS = 24
MAX_CACHE_ENTRIES_PER_TENANT = 1000


def _cache_key(tenant: str, query: str, filters: Optional[dict] = None) -> str:
    """Generate a deterministic cache key from query + filters."""
    payload = json.dumps({
        "tenant": tenant,
        "query": query.strip().lower(),
        "filters": filters or {},
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def get_cached_result(
    db: AsyncSession,
    tenant: str,
    query: str,
    filters: Optional[dict] = None,
) -> Optional[dict]:
    """Look up cached search results by semantic key.
    
    Returns cached dict if hit and not expired, else None.
    """
    try:
        key = _cache_key(tenant, query, filters)
        stmt = select(KnowledgeCacheEntry).where(
            KnowledgeCacheEntry.tenant == tenant,
            KnowledgeCacheEntry.cache_key == key,
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()
        
        if entry is None:
            return None
        
        # Check expiry — handle both naive and aware datetimes
        if entry.expires_at:
            exp = entry.expires_at
            now_utc = datetime.now(timezone.utc)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now_utc:
                return None
        
        # Update hit count
        entry.hit_count = (entry.hit_count or 0) + 1
        entry.last_hit_at = datetime.now(timezone.utc)
        await db.flush()
        
        return {
            "results": entry.results or [],
            "stored_at": entry.created_at.isoformat() if entry.created_at else None,
            "hit_count": entry.hit_count,
            "source_count": entry.source_count or 0,
        }
    except Exception as exc:
        logger.warning("get_cached_result failed: %s", exc)
        return None


async def store_in_cache(
    db: AsyncSession,
    tenant: str,
    query: str,
    results: list[dict],
    filters: Optional[dict] = None,
    *,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> str:
    """Store search results in cache with TTL.
    
    Returns cache_key string.
    """
    try:
        key = _cache_key(tenant, query, filters)
        now = datetime.now(timezone.utc)
        
        # Check if entry already exists, update it
        stmt = select(KnowledgeCacheEntry).where(
            KnowledgeCacheEntry.tenant == tenant,
            KnowledgeCacheEntry.cache_key == key,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        source_ids = set()
        for r in results:
            sid = r.get("source_id")
            if sid:
                source_ids.add(sid)
        
        if existing:
            existing.results = results
            existing.expires_at = now + timedelta(hours=ttl_hours)
            existing.source_count = len(source_ids)
            existing.hit_count = 0
            entry_id = existing.id
        else:
            entry = KnowledgeCacheEntry(
                id=uuid.uuid4(),
                tenant=tenant,
                cache_key=key,
                query_text=query[:2000],
                results=results,
                filters=filters or {},
                source_count=len(source_ids),
                expires_at=now + timedelta(hours=ttl_hours),
                hit_count=0,
            )
            db.add(entry)
            entry_id = entry.id
        
        await db.flush()
        return str(key)
    except Exception as exc:
        logger.warning("store_in_cache failed: %s", exc)
        return ""


async def invalidate_cache(
    db: AsyncSession,
    tenant: str,
    *,
    source_id: Optional[str] = None,
    document_id: Optional[str] = None,
) -> int:
    """Invalidate cache entries related to a source or document.
    
    Returns count of invalidated entries.
    """
    try:
        count = 0
        
        if source_id or document_id:
            # Find entries whose results reference this source/document
            stmt = select(KnowledgeCacheEntry).where(
                KnowledgeCacheEntry.tenant == tenant,
            )
            entries = (await db.execute(stmt)).scalars().all()
            
            for entry in entries:
                results = entry.results or []
                should_invalidate = False
                
                for r in results:
                    if source_id and r.get("source_id") == source_id:
                        should_invalidate = True
                        break
                    if document_id and r.get("document_id") == document_id:
                        should_invalidate = True
                        break
                
                if should_invalidate:
                    entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                    count += 1
            
            await db.flush()
        else:
            # Invalidate all for tenant
            stmt = update(KnowledgeCacheEntry).where(
                KnowledgeCacheEntry.tenant == tenant,
            ).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            result = await db.execute(stmt)
            count = result.rowcount or 0
            await db.flush()
        
        try:
            await emit_event("knowledge.cache.invalidated", {
                "source_id": source_id,
                "document_id": document_id,
                "entries_invalidated": count,
            }, tenant=tenant)
        except Exception:
            pass
        
        return count
    except Exception as exc:
        logger.warning("invalidate_cache failed: %s", exc)
        return 0


async def get_cache_stats(db: AsyncSession, tenant: str) -> dict:
    """Get cache statistics for a tenant."""
    try:
        total_stmt = select(func.count()).select_from(KnowledgeCacheEntry).where(
            KnowledgeCacheEntry.tenant == tenant,
        )
        total = (await db.execute(total_stmt)).scalar() or 0
        
        active_stmt = select(func.count()).select_from(KnowledgeCacheEntry).where(
            KnowledgeCacheEntry.tenant == tenant,
            KnowledgeCacheEntry.expires_at > datetime.now(timezone.utc),
        )
        active = (await db.execute(active_stmt)).scalar() or 0
        
        hits_stmt = select(func.sum(KnowledgeCacheEntry.hit_count)).where(
            KnowledgeCacheEntry.tenant == tenant,
        )
        total_hits = (await db.execute(hits_stmt)).scalar() or 0
        
        avg_hits_stmt = select(func.avg(KnowledgeCacheEntry.hit_count)).where(
            KnowledgeCacheEntry.tenant == tenant,
        )
        avg_hits = (await db.execute(avg_hits_stmt)).scalar() or 0.0
        
        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "total_hits": int(total_hits),
            "avg_hits_per_entry": round(float(avg_hits), 2),
        }
    except Exception as exc:
        logger.warning("get_cache_stats failed: %s", exc)
        return {"total_entries": 0, "active_entries": 0, "expired_entries": 0, "total_hits": 0, "avg_hits_per_entry": 0.0}


async def prune_expired_cache(db: AsyncSession, tenant: str) -> int:
    """Remove expired cache entries. Returns count of pruned entries."""
    try:
        stmt = delete(KnowledgeCacheEntry).where(
            KnowledgeCacheEntry.tenant == tenant,
            KnowledgeCacheEntry.expires_at < datetime.now(timezone.utc),
        )
        result = await db.execute(stmt)
        count = result.rowcount or 0
        await db.flush()
        return count
    except Exception as exc:
        logger.warning("prune_expired_cache failed: %s", exc)
        return 0
