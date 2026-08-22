"""Entity resolution: merge duplicates, resolve aliases."""
from __future__ import annotations


class EntityResolutionService:
    def __init__(self, entity_service=None, relationship_service=None):
        self._entity_svc = entity_service
        self._relationship_svc = relationship_service

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

    def _compute_similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        a_lower, b_lower = a.lower(), b.lower()
        if a_lower == b_lower:
            return 1.0

        def bigrams(s: str) -> set[str]:
            return {s[i : i + 2] for i in range(len(s) - 1)}

        sa, sb = bigrams(a_lower), bigrams(b_lower)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def find_duplicates(self, tenant: str, entity_type: str = "", threshold: float = 0.85) -> list[dict]:
        entities = self.entity_svc.list_entities(tenant=tenant, entity_type=entity_type, limit=10000, status="active")
        duplicates: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1 :]:
                pair = tuple(sorted([e1["id"], e2["id"]]))
                if pair in seen:
                    continue
                name_sim = self._compute_similarity(e1["name"], e2["name"])
                display_sim = self._compute_similarity(e1.get("display_name", ""), e2.get("display_name", ""))
                score = max(name_sim, display_sim * 0.95)
                if score >= threshold:
                    duplicates.append({
                        "entity_1": {"id": e1["id"], "name": e1["name"], "type": e1["entity_type"]},
                        "entity_2": {"id": e2["id"], "name": e2["name"], "type": e2["entity_type"]},
                        "similarity": round(score, 4),
                    })
                    seen.add(pair)
        return sorted(duplicates, key=lambda x: x["similarity"], reverse=True)

    def resolve_entities(self, tenant: str, entity_ids: list[str], merge_into: str = "") -> dict:
        if len(entity_ids) < 2:
            return {"error": "need at least 2 entities to merge"}
        entities = [e for e in (self.entity_svc.get_entity(eid) for eid in entity_ids) if e]
        if len(entities) < 2:
            return {"error": "not enough valid entities found"}
        if not merge_into:
            max_rels = -1
            for e in entities:
                rels = self.relationship_svc.get_relationships_for_entity(e["id"], direction="both", limit=1000)
                if len(rels) > max_rels:
                    max_rels = len(rels)
                    merge_into = e["id"]
        target = self.entity_svc.get_entity(merge_into)
        if not target:
            return {"error": "merge target not found"}
        aliases_moved = 0
        rels_repointed = 0
        for eid in entity_ids:
            if eid == merge_into:
                continue
            source = self.entity_svc.get_entity(eid)
            if not source:
                continue
            for alias in source.get("aliases", []):
                self.entity_svc.add_alias(merge_into, alias.get("type", ""), alias.get("value", ""), alias.get("source", ""))
                aliases_moved += 1
            for r in self.relationship_svc.get_relationships_for_entity(eid, direction="both", limit=1000):
                if r["source_entity_id"] == eid:
                    self.relationship_svc.update_relationship(r["id"], source_entity_id=merge_into)
                    rels_repointed += 1
                if r["target_entity_id"] == eid:
                    self.relationship_svc.update_relationship(r["id"], target_entity_id=merge_into)
                    rels_repointed += 1
            self.entity_svc.delete_entity(eid)
        return {"merged_into": merge_into, "entities_merged": len(entity_ids) - 1, "aliases_moved": aliases_moved, "relationships_repointed": rels_repointed}

    def find_canonical_id(self, tenant: str, external_id: str, provider: str) -> str | None:
        entity = self.entity_svc.get_entity_by_external_id(external_id, provider, tenant)
        return entity["id"] if entity else None

    def merge_by_external_id(self, tenant: str, external_ids: list[dict]) -> dict:
        merged = 0
        for item in external_ids:
            eid = item.get("external_id", "")
            prov = item.get("provider", "")
            if not eid or not prov:
                continue
            entities = self.entity_svc.list_entities(tenant=tenant, external_id=eid, provider=prov, limit=100, status="active")
            if len(entities) >= 2:
                ids = [e["id"] for e in entities]
                self.resolve_entities(tenant, ids, merge_into=ids[0])
                merged += 1
        return {"groups_merged": merged}

    def get_resolution_stats(self, tenant: str = "") -> dict:
        entities = self.entity_svc.list_entities(tenant=tenant, limit=10000, status="active")
        dupes = self.find_duplicates(tenant, threshold=0.85) if len(entities) <= 5000 else []
        return {"total_entities": len(entities), "potential_duplicates": len(dupes), "resolution_rate": 1.0 - (len(dupes) / max(len(entities), 1))}

    def auto_resolve(self, tenant: str, entity_type: str = "", threshold: float = 0.9) -> dict:
        dupes = self.find_duplicates(tenant, entity_type=entity_type, threshold=threshold)
        merged = 0
        for d in dupes:
            result = self.resolve_entities(tenant, [d["entity_1"]["id"], d["entity_2"]["id"]])
            if "error" not in result:
                merged += 1
        return {"candidates_found": len(dupes), "auto_merged": merged}


entity_resolution_service = EntityResolutionService()
