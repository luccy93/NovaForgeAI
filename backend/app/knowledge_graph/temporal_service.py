"""Temporal graph: track relationship validity over time."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemporalService:
    def __init__(self, entity_service=None, relationship_service=None):
        self._entity_svc = entity_service
        self._relationship_svc = relationship_service
        self._snapshots: list[dict] = []
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

    def get_relationship_at_time(self, relationship_id: str, timestamp: str) -> dict | None:
        rel = self.relationship_svc.get_relationship(relationship_id)
        if not rel:
            return None
        valid_from = rel.get("valid_from", "")
        valid_to = rel.get("valid_to", "")
        if valid_from and valid_from > timestamp:
            return None
        if valid_to and valid_to < timestamp:
            return None
        return rel

    def get_entity_history(self, entity_id: str) -> list[dict]:
        rels = self.relationship_svc.get_relationships_for_entity(entity_id, direction="both", limit=10000)
        history: list[dict] = []
        for r in rels:
            history.append({
                "relationship_id": r["id"],
                "source": r["source_entity_id"],
                "target": r["target_entity_id"],
                "type": r["relationship_type"],
                "valid_from": r.get("valid_from", ""),
                "valid_to": r.get("valid_to", ""),
                "observed_at": r.get("observed_at", ""),
                "is_active": r["is_active"],
            })
        return sorted(history, key=lambda x: x.get("valid_from", ""))

    def get_relationship_history(self, tenant: str, source_id: str = "", target_id: str = "", rel_type: str = "") -> list[dict]:
        return self.relationship_svc.list_relationships(
            tenant=tenant, source_entity_id=source_id, target_entity_id=target_id,
            relationship_type=rel_type, is_active=None, limit=10000,
        )

    def get_ownership_at_time(self, tenant: str, entity_id: str, timestamp: str) -> list[dict]:
        own_types = {"MEMBER_OF", "OWNS", "MAINTAINS", "APPROVES"}
        all_rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=None, limit=10000)
        results: list[dict] = []
        for r in all_rels:
            if r["relationship_type"] not in own_types:
                continue
            if r["target_entity_id"] != entity_id and r["source_entity_id"] != entity_id:
                continue
            if not self.get_relationship_at_time(r["id"], timestamp):
                continue
            owner_id = r["source_entity_id"] if r["target_entity_id"] == entity_id else r["target_entity_id"]
            owner = self.entity_svc.get_entity(owner_id)
            results.append({"owner_id": owner_id, "owner_name": owner["name"] if owner else owner_id, "ownership_type": r["relationship_type"], "valid_from": r.get("valid_from", ""), "valid_to": r.get("valid_to", "")})
        return results

    def get_deployments_at_time(self, tenant: str, service_id: str, timestamp: str) -> list[dict]:
        deploy_types = {"DEPLOYS", "BUILDS"}
        all_rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=None, limit=10000)
        results: list[dict] = []
        for r in all_rels:
            if r["relationship_type"] not in deploy_types:
                continue
            if r["target_entity_id"] != service_id:
                continue
            if not self.get_relationship_at_time(r["id"], timestamp):
                continue
            source = self.entity_svc.get_entity(r["source_entity_id"])
            results.append({"deployment_id": r["source_entity_id"], "deployment_name": source["name"] if source else r["source_entity_id"], "type": r["relationship_type"], "valid_from": r.get("valid_from", ""), "valid_to": r.get("valid_to", "")})
        return results

    def create_snapshot(self, tenant: str, name: str, description: str = "", snapshot_type: str = "manual", reference_id: str = "", reference_type: str = "") -> dict:
        entities = self.entity_svc.list_entities(tenant=tenant, limit=10000, status="active")
        relationships = self.relationship_svc.list_relationships(tenant=tenant, is_active=True, limit=10000)
        snapshot_id = str(uuid.uuid4())
        now = _now()
        snapshot = {
            "id": snapshot_id,
            "tenant": tenant,
            "name": name,
            "description": description,
            "snapshot_type": snapshot_type,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "data_json": {"entities": entities, "relationships": relationships},
            "created_at": now,
        }
        self._snapshots.append(snapshot)
        self._audit_log.append({"id": str(uuid.uuid4()), "tenant": tenant, "action": "snapshot_created", "entity_id": snapshot_id, "actor": "system", "details": {"name": name, "entity_count": len(entities)}, "timestamp": now})
        return snapshot

    def expire_relationship(self, relationship_id: str, valid_to: str = "") -> bool:
        result = self.relationship_svc.update_relationship(relationship_id, valid_to=valid_to or _now())
        return result is not None

    def validate_temporal_consistency(self, tenant: str = "") -> list[dict]:
        all_rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=None, limit=10000)
        issues: list[dict] = []
        for r in all_rels:
            if not r.get("valid_from"):
                issues.append({"type": "missing_valid_from", "relationship_id": r["id"], "relationship_type": r["relationship_type"]})
            if r.get("valid_to") and r.get("valid_from") and r["valid_to"] < r["valid_from"]:
                issues.append({"type": "invalid_time_range", "relationship_id": r["id"], "relationship_type": r["relationship_type"]})
        return issues

    def get_snapshot_data(self, tenant: str, snapshot_name: str = "") -> dict | None:
        for s in reversed(self._snapshots):
            if s["tenant"] == tenant:
                if not snapshot_name or s["name"] == snapshot_name:
                    return s
        return None


temporal_service = TemporalService()
