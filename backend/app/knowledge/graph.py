"""Knowledge Graph construction and entity resolution — Volume 68.

Provides entity extraction, deduplication, link creation, and graph
enrichment across ingested knowledge sources.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import emit_event, MAX_GRAPH_RESULTS
from app.knowledge.models import KnowledgeChunk, KnowledgeEntity, KnowledgeLink, KnowledgeDocument

logger = logging.getLogger(__name__)


async def resolve_entities(
    db: AsyncSession,
    tenant: str,
    document_id: uuid.UUID,
    raw_entities: list[dict],
) -> list[dict]:
    """Resolve raw extracted entities against existing entities, creating or updating as needed.

    raw_entities: [{"name": str, "entity_type": str, "description": str, "properties": dict, "confidence": float}]
    Returns: list of resolved entity dicts with id, name, entity_type, is_new, etc.
    """
    resolved: list[dict] = []
    for raw in raw_entities:
        name = (raw.get("name") or "").strip()
        entity_type = (raw.get("entity_type") or "UNKNOWN").strip()[:32]
        if not name:
            continue

        # Search for existing entity by name + type (case-insensitive)
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.tenant == tenant,
            func.lower(KnowledgeEntity.name) == name.lower(),
            KnowledgeEntity.entity_type == entity_type,
            KnowledgeEntity.status != "DELETED",
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        is_new = False
        if existing is None:
            # Create new entity
            entity = KnowledgeEntity(
                id=uuid.uuid4(),
                tenant=tenant,
                entity_type=entity_type,
                name=name,
                description=raw.get("description") or "",
                properties=raw.get("properties") or {},
                source_ids=[str(document_id)],
                classification=raw.get("classification", "INTERNAL"),
                confidence=min(max(float(raw.get("confidence", 0.5)), 0.0), 1.0),
                status="ACTIVE",
            )
            db.add(entity)
            await db.flush()
            is_new = True
            resolved.append({
                "id": str(entity.id),
                "name": name,
                "entity_type": entity_type,
                "is_new": True,
                "confidence": entity.confidence,
            })
        else:
            # Update existing: merge source_ids, boost confidence
            existing_sources = existing.source_ids or []
            doc_str = str(document_id)
            if doc_str not in existing_sources:
                existing_sources.append(doc_str)
                existing.source_ids = existing_sources

            new_conf = float(raw.get("confidence", 0.5))
            existing.confidence = min(max((existing.confidence + new_conf) / 2, 0.0), 1.0)

            if raw.get("description") and len(raw["description"]) > len(existing.description or ""):
                existing.description = raw["description"]

            props = existing.properties or {}
            props.update(raw.get("properties") or {})
            existing.properties = props

            await db.flush()
            resolved.append({
                "id": str(existing.id),
                "name": name,
                "entity_type": entity_type,
                "is_new": False,
                "confidence": existing.confidence,
            })

    return resolved


async def create_entity_links(
    db: AsyncSession,
    tenant: str,
    document_id: uuid.UUID,
    entity_pairs: list[dict],
) -> list[dict]:
    """Create or strengthen links between entities that co-occur in a document.

    entity_pairs: [{"source_id": str, "target_id": str, "link_type": str, "weight": float, "properties": dict}]
    Returns: list of created/updated link dicts.
    """
    created: list[dict] = []
    for pair in entity_pairs:
        src = pair.get("source_id")
        tgt = pair.get("target_id")
        if not src or not tgt or src == tgt:
            continue

        try:
            src_uuid = uuid.UUID(src)
            tgt_uuid = uuid.UUID(tgt)
        except (ValueError, TypeError):
            continue

        # Check for existing link (either direction)
        stmt = select(KnowledgeLink).where(
            KnowledgeLink.tenant == tenant,
            ((KnowledgeLink.source_entity_id == src_uuid) & (KnowledgeLink.target_entity_id == tgt_uuid))
            | ((KnowledgeLink.source_entity_id == tgt_uuid) & (KnowledgeLink.target_entity_id == src_uuid)),
            KnowledgeLink.link_type == pair.get("link_type", "RELATED_TO"),
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is None:
            link = KnowledgeLink(
                id=uuid.uuid4(),
                tenant=tenant,
                source_entity_id=src_uuid,
                target_entity_id=tgt_uuid,
                link_type=pair.get("link_type", "RELATED_TO"),
                weight=min(max(float(pair.get("weight", 1.0)), 0.0), 10.0),
                properties=pair.get("properties") or {},
                classification=pair.get("classification", "INTERNAL"),
            )
            db.add(link)
            await db.flush()
            created.append({
                "id": str(link.id),
                "source_entity_id": src,
                "target_entity_id": tgt,
                "link_type": link.link_type,
                "weight": link.weight,
                "is_new": True,
            })
        else:
            # Strengthen existing link
            existing.weight = min(existing.weight + float(pair.get("weight", 0.5)), 10.0)
            props = existing.properties or {}
            props.update(pair.get("properties") or {})
            existing.properties = props
            await db.flush()
            created.append({
                "id": str(existing.id),
                "source_entity_id": str(existing.source_entity_id),
                "target_entity_id": str(existing.target_entity_id),
                "link_type": existing.link_type,
                "weight": existing.weight,
                "is_new": False,
            })

    return created


async def get_entity_neighbors(
    db: AsyncSession,
    tenant: str,
    entity_id: uuid.UUID,
    *,
    depth: int = 1,
    direction: str = "both",
    classification_max: str = "SECRET",
    limit: int = MAX_GRAPH_RESULTS,
) -> dict:
    """Get entity and its neighborhood up to `depth` hops.

    Returns: {"entity": {...}, "neighbors": [...], "links": [...], "depth": int}
    """
    from app.knowledge.authz import CLASSIFICATION_LEVELS

    max_level = CLASSIFICATION_LEVELS.get(classification_max, 3)
    visited_entities: set[str] = set()
    all_neighbors: list[dict] = []
    all_links: list[dict] = []

    # Get the root entity
    stmt = select(KnowledgeEntity).where(
        KnowledgeEntity.id == entity_id,
        KnowledgeEntity.tenant == tenant,
        KnowledgeEntity.status != "DELETED",
    )
    result = await db.execute(stmt)
    root = result.scalar_one_or_none()
    if root is None:
        return {"entity": None, "neighbors": [], "links": [], "depth": 0}

    root_dict = {
        "id": str(root.id), "name": root.name, "entity_type": root.entity_type,
        "description": root.description, "confidence": root.confidence,
        "classification": root.classification, "properties": root.properties,
    }

    current_ids: list[uuid.UUID] = [entity_id]
    visited_entities.add(str(entity_id))

    for hop in range(depth):
        if not current_ids or len(all_neighbors) >= limit:
            break

        next_ids: list[uuid.UUID] = []

        for eid in current_ids:
            # Outgoing links
            if direction in ("both", "outgoing"):
                stmt = (
                    select(KnowledgeLink, KnowledgeEntity)
                    .join(KnowledgeEntity, KnowledgeLink.target_entity_id == KnowledgeEntity.id)
                    .where(
                        KnowledgeLink.source_entity_id == eid,
                        KnowledgeLink.tenant == tenant,
                        KnowledgeEntity.status != "DELETED",
                    )
                    .order_by(KnowledgeLink.weight.desc())
                    .limit(limit - len(all_neighbors))
                )
                rows = (await db.execute(stmt)).fetchall()
                for link, entity in rows:
                    eid_str = str(entity.id)
                    if eid_str in visited_entities:
                        continue
                    cl = CLASSIFICATION_LEVELS.get(entity.classification, 1)
                    if cl > max_level:
                        continue
                    visited_entities.add(eid_str)
                    all_neighbors.append({
                        "id": eid_str, "name": entity.name, "entity_type": entity.entity_type,
                        "description": entity.description, "confidence": entity.confidence,
                        "classification": entity.classification, "hop": hop + 1,
                    })
                    all_links.append({
                        "id": str(link.id), "source": str(eid), "target": eid_str,
                        "link_type": link.link_type, "weight": link.weight,
                    })
                    next_ids.append(entity.id)

            # Incoming links
            if direction in ("both", "incoming"):
                stmt = (
                    select(KnowledgeLink, KnowledgeEntity)
                    .join(KnowledgeEntity, KnowledgeLink.source_entity_id == KnowledgeEntity.id)
                    .where(
                        KnowledgeLink.target_entity_id == eid,
                        KnowledgeLink.tenant == tenant,
                        KnowledgeEntity.status != "DELETED",
                    )
                    .order_by(KnowledgeLink.weight.desc())
                    .limit(limit - len(all_neighbors))
                )
                rows = (await db.execute(stmt)).fetchall()
                for link, entity in rows:
                    eid_str = str(entity.id)
                    if eid_str in visited_entities:
                        continue
                    cl = CLASSIFICATION_LEVELS.get(entity.classification, 1)
                    if cl > max_level:
                        continue
                    visited_entities.add(eid_str)
                    all_neighbors.append({
                        "id": eid_str, "name": entity.name, "entity_type": entity.entity_type,
                        "description": entity.description, "confidence": entity.confidence,
                        "classification": entity.classification, "hop": hop + 1,
                    })
                    all_links.append({
                        "id": str(link.id), "source": eid_str, "target": str(eid),
                        "link_type": link.link_type, "weight": link.weight,
                    })
                    next_ids.append(entity.id)

        current_ids = next_ids

    return {
        "entity": root_dict,
        "neighbors": all_neighbors[:limit],
        "links": all_links[:limit],
        "depth": depth,
    }


async def merge_entities(
    db: AsyncSession,
    tenant: str,
    primary_id: uuid.UUID,
    duplicate_ids: list[uuid.UUID],
) -> dict:
    """Merge duplicate entities into a primary entity.

    Transfers all links and source_ids from duplicates to primary, then soft-deletes duplicates.
    Returns: {"primary_id": str, "merged_count": int, "links_transferred": int}
    """
    stmt = select(KnowledgeEntity).where(
        KnowledgeEntity.id == primary_id,
        KnowledgeEntity.tenant == tenant,
        KnowledgeEntity.status != "DELETED",
    )
    result = await db.execute(stmt)
    primary = result.scalar_one_or_none()
    if primary is None:
        raise ValueError(f"Primary entity {primary_id} not found")

    merged_count = 0
    links_transferred = 0
    primary_sources = set(primary.source_ids or [])
    primary_props = primary.properties or {}

    for dup_id in duplicate_ids:
        if dup_id == primary_id:
            continue

        dup_stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.id == dup_id,
            KnowledgeEntity.tenant == tenant,
            KnowledgeEntity.status != "DELETED",
        )
        dup_result = await db.execute(dup_stmt)
        dup = dup_result.scalar_one_or_none()
        if dup is None:
            continue

        # Transfer source_ids
        for sid in (dup.source_ids or []):
            primary_sources.add(sid)

        # Merge properties (primary wins on conflict)
        for k, v in (dup.properties or {}).items():
            if k not in primary_props:
                primary_props[k] = v

        # Boost confidence
        primary.confidence = min(max((primary.confidence + dup.confidence) / 2, 0.0), 1.0)

        # Transfer description if longer
        if dup.description and len(dup.description) > len(primary.description or ""):
            primary.description = dup.description

        # Transfer links
        out_stmt = select(KnowledgeLink).where(
            KnowledgeLink.tenant == tenant,
            KnowledgeLink.source_entity_id == dup_id,
        )
        out_links = (await db.execute(out_stmt)).scalars().all()
        for link in out_links:
            link.source_entity_id = primary_id
            links_transferred += 1

        in_stmt = select(KnowledgeLink).where(
            KnowledgeLink.tenant == tenant,
            KnowledgeLink.target_entity_id == dup_id,
        )
        in_links = (await db.execute(in_stmt)).scalars().all()
        for link in in_links:
            link.target_entity_id = primary_id
            links_transferred += 1

        # Soft-delete duplicate
        dup.status = "DELETED"
        merged_count += 1

    primary.source_ids = list(primary_sources)
    primary.properties = primary_props
    await db.flush()

    try:
        await emit_event("knowledge.entities.merged", {
            "primary_id": str(primary_id),
            "merged_count": merged_count,
            "links_transferred": links_transferred,
        }, tenant=tenant)
    except Exception:
        pass

    return {
        "primary_id": str(primary_id),
        "merged_count": merged_count,
        "links_transferred": links_transferred,
    }


async def get_graph_stats(db: AsyncSession, tenant: str) -> dict:
    """Get aggregate statistics for the knowledge graph."""
    try:
        ent_stmt = select(func.count(KnowledgeEntity.id)).where(
            KnowledgeEntity.tenant == tenant,
            KnowledgeEntity.status != "DELETED",
        )
        ent_count = (await db.execute(ent_stmt)).scalar() or 0
        
        link_stmt = select(func.count(KnowledgeLink.id)).where(
            KnowledgeLink.tenant == tenant,
        )
        link_count = (await db.execute(link_stmt)).scalar() or 0
        
        type_stmt = (
            select(KnowledgeEntity.entity_type, func.count(KnowledgeEntity.id))
            .where(KnowledgeEntity.tenant == tenant, KnowledgeEntity.status != "DELETED")
            .group_by(KnowledgeEntity.entity_type)
        )
        type_rows = (await db.execute(type_stmt)).fetchall()
        by_type = {row[0]: row[1] for row in type_rows}
        
        avg_conf_stmt = select(func.avg(KnowledgeEntity.confidence)).where(
            KnowledgeEntity.tenant == tenant,
            KnowledgeEntity.status != "DELETED",
        )
        avg_confidence = (await db.execute(avg_conf_stmt)).scalar() or 0.0

        return {
            "entity_count": ent_count,
            "link_count": link_count,
            "entities_by_type": by_type,
            "avg_confidence": round(float(avg_confidence), 4),
        }
    except Exception as exc:
        logger.warning("get_graph_stats failed: %s", exc)
        return {"entity_count": 0, "link_count": 0, "entities_by_type": {}, "avg_confidence": 0.0}
