"""Release history and graph — KG relationships."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.models import ReleaseRecord


class HistoryService:
    async def record_history(self, db: AsyncSession, release_id: str, event_type: str, data: dict) -> ReleaseRecord | None:
        rec = await db.get(ReleaseRecord, release_id)
        if not rec:
            return None
        hist = rec.metadata_json or {}
        events = hist.get("history", [])
        events.append({"type": event_type, "data": data})
        hist["history"] = events
        rec.metadata_json = hist
        await db.flush()
        # Try KG
        try:
            from app.knowledge_graph.entity_service import entity_service
            from app.knowledge_graph.relationship_service import relationship_service
            await entity_service.create_entity(tenant=rec.tenant, entity_type="release", external_id=str(rec.id), name=f"{rec.service}:{rec.version}", metadata_json={"event": event_type})
        except Exception:
            pass
        return rec

    async def get_history(self, db: AsyncSession, release_id: str) -> list:
        rec = await db.get(ReleaseRecord, release_id)
        if not rec:
            return []
        return (rec.metadata_json or {}).get("history", [])

    async def get_graph(self, db: AsyncSession, release_id: str) -> dict:
        rec = await db.get(ReleaseRecord, release_id)
        if not rec:
            return {}
        # Chain commit->PR->build->artifact->release->deployment->env
        chain = {
            "commit": rec.commit_sha,
            "build": rec.build_id,
            "artifact": str(rec.artifact_id) if rec.artifact_id else None,
            "release": str(rec.id),
            "service": rec.service,
            "environment": rec.environment,
        }
        # Try KG relationships
        try:
            from app.knowledge_graph.relationship_service import relationship_service
            rels = await relationship_service.get_relationships_for_entity(str(rec.id), direction="both")
            chain["relationships"] = len(rels) if rels else 0
        except Exception:
            chain["relationships"] = 0
        return chain
