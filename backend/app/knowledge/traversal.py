"""Graph traversal and pathfinding — Volume 68.

Provides multi-hop traversal, shortest path, neighborhood expansion,
and community detection over the knowledge graph with ACL filtering.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import MAX_GRAPH_DEPTH, MAX_GRAPH_RESULTS, emit_event
from app.knowledge.models import KnowledgeEntity, KnowledgeLink

logger = logging.getLogger(__name__)


async def traverse_graph(
    db: AsyncSession,
    tenant: str,
    start_entity_id: uuid.UUID,
    *,
    depth: int = 2,
    direction: str = "both",
    entity_types: Optional[list[str]] = None,
    link_types: Optional[list[str]] = None,
    classification_max: str = "SECRET",
    limit: int = MAX_GRAPH_RESULTS,
) -> dict:
    """Multi-hop BFS traversal from a starting entity.

    Returns: {"nodes": [...], "edges": [...], "paths_explored": int, "depth_reached": int}
    """
    from app.knowledge.authz import CLASSIFICATION_LEVELS

    depth = min(max(depth, 1), MAX_GRAPH_DEPTH)
    max_level = CLASSIFICATION_LEVELS.get(classification_max, 3)

    visited: dict[str, dict] = {}
    edges: list[dict] = []
    queue: deque[tuple[uuid.UUID, int]] = deque()
    queue.append((start_entity_id, 0))

    # Seed with root
    stmt = select(KnowledgeEntity).where(
        KnowledgeEntity.id == start_entity_id,
        KnowledgeEntity.tenant == tenant,
        KnowledgeEntity.status != "DELETED",
    )
    result = await db.execute(stmt)
    root = result.scalar_one_or_none()
    if root is None:
        return {"nodes": [], "edges": [], "paths_explored": 0, "depth_reached": 0}

    visited[str(root.id)] = {
        "id": str(root.id), "name": root.name, "entity_type": root.entity_type,
        "description": root.description, "confidence": root.confidence,
        "classification": root.classification, "hop": 0,
    }

    paths_explored = 0

    while queue and len(visited) < limit:
        current_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue

        paths_explored += 1

        # Outgoing
        if direction in ("both", "outgoing"):
            stmt = (
                select(KnowledgeLink, KnowledgeEntity)
                .join(KnowledgeEntity, KnowledgeLink.target_entity_id == KnowledgeEntity.id)
                .where(
                    KnowledgeLink.source_entity_id == current_id,
                    KnowledgeLink.tenant == tenant,
                    KnowledgeEntity.status != "DELETED",
                )
            )
            if link_types:
                stmt = stmt.where(KnowledgeLink.link_type.in_(link_types))
            stmt = stmt.order_by(KnowledgeLink.weight.desc()).limit(limit)
            rows = (await db.execute(stmt)).fetchall()

            for link, entity in rows:
                eid_str = str(entity.id)
                cl = CLASSIFICATION_LEVELS.get(entity.classification, 1)
                if cl > max_level:
                    continue
                if entity_types and entity.entity_type not in entity_types:
                    continue

                edges.append({
                    "id": str(link.id), "source": str(current_id), "target": eid_str,
                    "link_type": link.link_type, "weight": link.weight,
                })

                if eid_str not in visited:
                    visited[eid_str] = {
                        "id": eid_str, "name": entity.name, "entity_type": entity.entity_type,
                        "description": entity.description, "confidence": entity.confidence,
                        "classification": entity.classification, "hop": current_depth + 1,
                    }
                    queue.append((entity.id, current_depth + 1))

        # Incoming
        if direction in ("both", "incoming"):
            stmt = (
                select(KnowledgeLink, KnowledgeEntity)
                .join(KnowledgeEntity, KnowledgeLink.source_entity_id == KnowledgeEntity.id)
                .where(
                    KnowledgeLink.target_entity_id == current_id,
                    KnowledgeLink.tenant == tenant,
                    KnowledgeEntity.status != "DELETED",
                )
            )
            if link_types:
                stmt = stmt.where(KnowledgeLink.link_type.in_(link_types))
            stmt = stmt.order_by(KnowledgeLink.weight.desc()).limit(limit)
            rows = (await db.execute(stmt)).fetchall()

            for link, entity in rows:
                eid_str = str(entity.id)
                cl = CLASSIFICATION_LEVELS.get(entity.classification, 1)
                if cl > max_level:
                    continue
                if entity_types and entity.entity_type not in entity_types:
                    continue

                edges.append({
                    "id": str(link.id), "source": eid_str, "target": str(current_id),
                    "link_type": link.link_type, "weight": link.weight,
                })

                if eid_str not in visited:
                    visited[eid_str] = {
                        "id": eid_str, "name": entity.name, "entity_type": entity.entity_type,
                        "description": entity.description, "confidence": entity.confidence,
                        "classification": entity.classification, "hop": current_depth + 1,
                    }
                    queue.append((entity.id, current_depth + 1))

    return {
        "nodes": list(visited.values())[:limit],
        "edges": edges[:limit],
        "paths_explored": paths_explored,
        "depth_reached": min(depth, max((n["hop"] for n in visited.values()), default=0)),
    }


async def find_shortest_path(
    db: AsyncSession,
    tenant: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    *,
    max_depth: int = MAX_GRAPH_DEPTH,
    direction: str = "both",
) -> dict:
    """BFS shortest path between two entities.

    Returns: {"path": [entity_dicts], "edges": [link_dicts], "distance": int} or empty if no path.
    """
    max_depth = min(max(max_depth, 1), MAX_GRAPH_DEPTH)

    # Verify both entities exist
    for eid in (source_id, target_id):
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.id == eid,
            KnowledgeEntity.tenant == tenant,
            KnowledgeEntity.status != "DELETED",
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            return {"path": [], "edges": [], "distance": -1}

    # BFS with parent tracking
    parent: dict[str, tuple[str, str]] = {}  # child_id -> (parent_id, link_id)
    visited: set[str] = {str(source_id)}
    queue: deque[tuple[uuid.UUID, int]] = deque()
    queue.append((source_id, 0))

    found = False

    while queue:
        current_id, current_depth = queue.popleft()
        if current_depth >= max_depth:
            continue

        # Outgoing
        if direction in ("both", "outgoing"):
            stmt = select(KnowledgeLink).where(
                KnowledgeLink.source_entity_id == current_id,
                KnowledgeLink.tenant == tenant,
            )
            links = (await db.execute(stmt)).scalars().all()
            for link in links:
                target_str = str(link.target_entity_id)
                if target_str in visited:
                    continue
                visited.add(target_str)
                parent[target_str] = (str(current_id), str(link.id))
                if link.target_entity_id == target_id:
                    found = True
                    break
                queue.append((link.target_entity_id, current_depth + 1))
            if found:
                break

        # Incoming
        if direction in ("both", "incoming"):
            stmt = select(KnowledgeLink).where(
                KnowledgeLink.target_entity_id == current_id,
                KnowledgeLink.tenant == tenant,
            )
            links = (await db.execute(stmt)).scalars().all()
            for link in links:
                source_str = str(link.source_entity_id)
                if source_str in visited:
                    continue
                visited.add(source_str)
                parent[source_str] = (str(current_id), str(link.id))
                if link.source_entity_id == target_id:
                    found = True
                    break
                queue.append((link.source_entity_id, current_depth + 1))
            if found:
                break

    if not found:
        return {"path": [], "edges": [], "distance": -1}

    # Reconstruct path
    path_ids: list[str] = []
    edge_ids: list[str] = []
    current = str(target_id)
    while current != str(source_id):
        path_ids.append(current)
        if current in parent:
            parent_id, link_id = parent[current]
            edge_ids.append(link_id)
            current = parent_id
        else:
            break
    path_ids.append(str(source_id))
    path_ids.reverse()
    edge_ids.reverse()

    # Fetch entity details
    path_entities = []
    for pid in path_ids:
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.id == uuid.UUID(pid),
            KnowledgeEntity.tenant == tenant,
        )
        result = await db.execute(stmt)
        ent = result.scalar_one_or_none()
        if ent:
            path_entities.append({
                "id": str(ent.id), "name": ent.name, "entity_type": ent.entity_type,
                "description": ent.description, "confidence": ent.confidence,
            })

    # Fetch edge details
    edge_details = []
    for eid in edge_ids:
        stmt = select(KnowledgeLink).where(KnowledgeLink.id == uuid.UUID(eid))
        result = await db.execute(stmt)
        link = result.scalar_one_or_none()
        if link:
            edge_details.append({
                "id": str(link.id), "source": str(link.source_entity_id),
                "target": str(link.target_entity_id), "link_type": link.link_type,
                "weight": link.weight,
            })

    return {
        "path": path_entities,
        "edges": edge_details,
        "distance": len(path_entities) - 1,
    }


async def expand_neighborhood(
    db: AsyncSession,
    tenant: str,
    entity_ids: list[uuid.UUID],
    *,
    hops: int = 1,
    max_results: int = MAX_GRAPH_RESULTS,
    classification_max: str = "SECRET",
) -> dict:
    """Expand a set of entities by their neighbors (union expansion).

    Returns: {"seed_count": int, "expanded_count": int, "nodes": [...], "edges": [...]}
    """
    from app.knowledge.authz import CLASSIFICATION_LEVELS

    hops = min(max(hops, 1), MAX_GRAPH_DEPTH)
    max_level = CLASSIFICATION_LEVELS.get(classification_max, 3)

    visited: dict[str, dict] = {}
    all_edges: list[dict] = []
    current_ids: set[uuid.UUID] = set(entity_ids)

    # Load seed entities
    for eid in entity_ids:
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.id == eid, KnowledgeEntity.tenant == tenant,
            KnowledgeEntity.status != "DELETED",
        )
        result = await db.execute(stmt)
        ent = result.scalar_one_or_none()
        if ent:
            visited[str(ent.id)] = {
                "id": str(ent.id), "name": ent.name, "entity_type": ent.entity_type,
                "description": ent.description, "confidence": ent.confidence,
                "classification": ent.classification, "is_seed": True,
            }

    for hop in range(hops):
        if len(visited) >= max_results:
            break

        next_ids: set[uuid.UUID] = set()
        for eid in current_ids:
            # Outgoing
            stmt = (
                select(KnowledgeLink, KnowledgeEntity)
                .join(KnowledgeEntity, KnowledgeLink.target_entity_id == KnowledgeEntity.id)
                .where(
                    KnowledgeLink.source_entity_id == eid,
                    KnowledgeLink.tenant == tenant,
                    KnowledgeEntity.status != "DELETED",
                )
                .order_by(KnowledgeLink.weight.desc())
                .limit(max_results - len(visited))
            )
            rows = (await db.execute(stmt)).fetchall()
            for link, entity in rows:
                eid_str = str(entity.id)
                cl = CLASSIFICATION_LEVELS.get(entity.classification, 1)
                if cl > max_level:
                    continue
                all_edges.append({
                    "id": str(link.id), "source": str(eid), "target": eid_str,
                    "link_type": link.link_type, "weight": link.weight,
                })
                if eid_str not in visited:
                    visited[eid_str] = {
                        "id": eid_str, "name": entity.name, "entity_type": entity.entity_type,
                        "description": entity.description, "confidence": entity.confidence,
                        "classification": entity.classification, "is_seed": False,
                    }
                    next_ids.add(entity.id)

            # Incoming
            stmt = (
                select(KnowledgeLink, KnowledgeEntity)
                .join(KnowledgeEntity, KnowledgeLink.source_entity_id == KnowledgeEntity.id)
                .where(
                    KnowledgeLink.target_entity_id == eid,
                    KnowledgeLink.tenant == tenant,
                    KnowledgeEntity.status != "DELETED",
                )
                .order_by(KnowledgeLink.weight.desc())
                .limit(max_results - len(visited))
            )
            rows = (await db.execute(stmt)).fetchall()
            for link, entity in rows:
                eid_str = str(entity.id)
                cl = CLASSIFICATION_LEVELS.get(entity.classification, 1)
                if cl > max_level:
                    continue
                all_edges.append({
                    "id": str(link.id), "source": eid_str, "target": str(eid),
                    "link_type": link.link_type, "weight": link.weight,
                })
                if eid_str not in visited:
                    visited[eid_str] = {
                        "id": eid_str, "name": entity.name, "entity_type": entity.entity_type,
                        "description": entity.description, "confidence": entity.confidence,
                        "classification": entity.classification, "is_seed": False,
                    }
                    next_ids.add(entity.id)

        current_ids = next_ids

    return {
        "seed_count": len(entity_ids),
        "expanded_count": len(visited) - len(entity_ids),
        "nodes": list(visited.values())[:max_results],
        "edges": all_edges[:max_results],
    }


async def rank_entities_by_centrality(
    db: AsyncSession,
    tenant: str,
    *,
    entity_type: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Simple degree-centrality ranking of entities.

    Returns entities ranked by (in_degree + out_degree) * confidence.
    """
    stmt = select(KnowledgeEntity).where(
        KnowledgeEntity.tenant == tenant,
        KnowledgeEntity.status != "DELETED",
    )
    if entity_type:
        stmt = stmt.where(KnowledgeEntity.entity_type == entity_type)

    entities = (await db.execute(stmt)).scalars().all()

    ranked: list[dict] = []
    for ent in entities:
        # Count out-degree
        out_stmt = select(func.count()).select_from(KnowledgeLink).where(
            KnowledgeLink.source_entity_id == ent.id,
            KnowledgeLink.tenant == tenant,
        )
        out_degree = (await db.execute(out_stmt)).scalar() or 0

        # Count in-degree
        in_stmt = select(func.count()).select_from(KnowledgeLink).where(
            KnowledgeLink.target_entity_id == ent.id,
            KnowledgeLink.tenant == tenant,
        )
        in_degree = (await db.execute(in_stmt)).scalar() or 0

        centrality = (out_degree + in_degree) * (ent.confidence or 0.5)

        ranked.append({
            "id": str(ent.id), "name": ent.name, "entity_type": ent.entity_type,
            "description": ent.description, "confidence": ent.confidence,
            "in_degree": in_degree, "out_degree": out_degree,
            "centrality_score": round(centrality, 4),
        })

    ranked.sort(key=lambda x: x["centrality_score"], reverse=True)
    return ranked[:limit]
