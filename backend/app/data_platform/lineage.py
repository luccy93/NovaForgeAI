"""Lineage — source→dataset→transformation→output, column lineage, provenance."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataLineageEdge


async def record_edge(db: AsyncSession, tenant: str, source: str, target: str, transformation: str | None = None, pipeline_id: str | None = None, column_lineage: dict | None = None, provenance: dict | None = None) -> DataLineageEdge:
    if not source or not target:
        raise ValueError("source and target required")
    pid = None
    if pipeline_id:
        try:
            pid = uuid.UUID(pipeline_id)
        except Exception:
            pid = None
    edge = DataLineageEdge(
        tenant=tenant,
        source=source,
        target=target,
        transformation=transformation,
        pipeline_id=pid,
        version="1.0",
        provenance=provenance or {"source": source, "timestamp": datetime.now(timezone.utc).isoformat()},
        column_lineage=column_lineage or {},
    )
    # Also write to governance lineage for compliance if available
    try:
        from app.datagov.lineage import lineage_service
        async with db.begin_nested():
            await lineage_service.record_edge(db, tenant, source, target, transformation or "unknown", evidence=f"pipeline {pipeline_id}", stage="transform")
    except Exception:
        pass
    # Also write to knowledge graph
    try:
        from app.knowledge_graph.relationship_service import relationship_service
        async with db.begin_nested():
            await relationship_service.create_relationship(db, tenant, source, target, "lineage", confidence="confirmed", evidence=[provenance or {}])
    except Exception:
        pass
    db.add(edge)
    await db.flush()
    return edge


async def get_upstream(db: AsyncSession, tenant: str, node: str, depth: int = 5) -> list[DataLineageEdge]:
    visited = set()
    result = []
    queue = [(node, 0)]
    while queue:
        current, d = queue.pop(0)
        if d >= depth or current in visited:
            continue
        visited.add(current)
        q = select(DataLineageEdge).where(DataLineageEdge.tenant == tenant, DataLineageEdge.target == current)
        res = await db.execute(q)
        edges = res.scalars().all()
        for e in edges:
            result.append(e)
            queue.append((e.source, d + 1))
    return result


async def get_downstream(db: AsyncSession, tenant: str, node: str, depth: int = 5) -> list[DataLineageEdge]:
    visited = set()
    result = []
    queue = [(node, 0)]
    while queue:
        current, d = queue.pop(0)
        if d >= depth or current in visited:
            continue
        visited.add(current)
        q = select(DataLineageEdge).where(DataLineageEdge.tenant == tenant, DataLineageEdge.source == current)
        res = await db.execute(q)
        edges = res.scalars().all()
        for e in edges:
            result.append(e)
            queue.append((e.target, d + 1))
    return result


async def get_lineage_graph(db: AsyncSession, tenant: str, node: str, depth: int = 3) -> dict:
    ups = await get_upstream(db, tenant, node, depth)
    downs = await get_downstream(db, tenant, node, depth)
    return {"node": node, "upstream": [{"source": e.source, "target": e.target, "transformation": e.transformation} for e in ups], "downstream": [{"source": e.source, "target": e.target} for e in downs], "provenance": [e.provenance for e in ups+downs][:5]}
