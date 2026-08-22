"""Evidence and provenance tracking for the Knowledge Graph."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceService:
    def __init__(self, entity_service=None, relationship_service=None):
        self._entity_svc = entity_service
        self._relationship_svc = relationship_service
        self._audit_log: list[dict] = []

    @property
    def entity_svc(self):
        if self._entity_svc is None:
            from app.knowledge_graph.entity_service import entity_service
            self._entity_svc = entity_service
        return self._entity_svc

    @property
    def relationship_svc(self):
        if self._relationship_svc is None:
            from app.knowledge_graph.relationship_service import relationship_service
            self._relationship_svc = relationship_service
        return self._relationship_svc

    def add_evidence(self, relationship_id: str, evidence_source: str, evidence_data: dict, actor: str = "") -> dict:
        entry = self.relationship_svc.add_evidence(relationship_id, evidence_source, evidence_data, actor)
        if "error" not in entry:
            self._audit_log.append({
                "id": str(uuid.uuid4()),
                "action": "evidence_added",
                "entity_id": relationship_id,
                "actor": actor,
                "details": {"source": evidence_source},
                "timestamp": _now(),
            })
        return entry

    def get_evidence(self, relationship_id: str) -> list[dict]:
        rel = self.relationship_svc.get_relationship(relationship_id)
        return list(rel.get("evidence", [])) if rel else []

    def validate_evidence(self, relationship_id: str) -> dict:
        rel = self.relationship_svc.get_relationship(relationship_id)
        if not rel:
            return {"error": "relationship not found"}
        evidence = rel.get("evidence", [])
        sources = list({e.get("source", "unknown") for e in evidence})
        return {"has_evidence": len(evidence) > 0, "evidence_count": len(evidence), "sources": sources, "confidence": rel.get("confidence", "unknown")}

    def get_entity_provenance(self, entity_id: str) -> dict:
        rels = self.relationship_svc.get_relationships_for_entity(entity_id, direction="both", limit=1000)
        all_evidence: list[dict] = []
        for r in rels:
            for ev in r.get("evidence", []):
                all_evidence.append({**ev, "relationship_id": r["id"], "relationship_type": r["relationship_type"]})
        sources = list({e.get("source", "unknown") for e in all_evidence})
        return {"entity_id": entity_id, "evidence_count": len(all_evidence), "sources": sources, "evidence": all_evidence}

    def get_relationship_provenance(self, relationship_id: str) -> dict:
        rel = self.relationship_svc.get_relationship(relationship_id)
        if not rel:
            return {"error": "relationship not found"}
        return {"relationship_id": relationship_id, "source_entity_id": rel["source_entity_id"], "target_entity_id": rel["target_entity_id"], "relationship_type": rel["relationship_type"], "confidence": rel.get("confidence", "unknown"), "evidence": rel.get("evidence", [])}

    def verify_evidence_integrity(self, tenant: str = "") -> list[dict]:
        rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=True, limit=10000)
        missing: list[dict] = []
        for r in rels:
            if not r.get("evidence"):
                missing.append({"relationship_id": r["id"], "source_entity_id": r["source_entity_id"], "target_entity_id": r["target_entity_id"], "relationship_type": r["relationship_type"]})
        return missing

    def get_evidence_summary(self, tenant: str = "") -> dict:
        rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=True, limit=10000)
        total = len(rels)
        with_evidence = 0
        by_source: dict[str, int] = {}
        for r in rels:
            evidence = r.get("evidence", [])
            if evidence:
                with_evidence += 1
            for ev in evidence:
                src = ev.get("source", "unknown")
                by_source[src] = by_source.get(src, 0) + 1
        return {"total_relationships": total, "with_evidence": with_evidence, "without_evidence": total - with_evidence, "evidence_coverage": with_evidence / max(total, 1), "by_source": by_source}

    def track_event_bus_evidence(self, tenant: str, event_type: str, event_data: dict, entity_id: str = "") -> dict:
        record = {
            "id": str(uuid.uuid4()),
            "tenant": tenant,
            "event_type": event_type,
            "event_data": event_data,
            "entity_id": entity_id,
            "timestamp": _now(),
            "source": "event_bus",
        }
        self._audit_log.append({"id": str(uuid.uuid4()), "tenant": tenant, "action": "event_bus_evidence", "entity_id": entity_id, "actor": "event_bus", "details": {"event_type": event_type}, "timestamp": _now()})
        return record

    def get_audit_trail(self, tenant: str, entity_id: str = "", limit: int = 100) -> list[dict]:
        results: list[dict] = []
        for entry in reversed(self._audit_log):
            if tenant and entry.get("tenant") != tenant:
                continue
            if entity_id and entry.get("entity_id") != entity_id:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results


evidence_service = EvidenceService()
