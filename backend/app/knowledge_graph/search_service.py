"""Search service for the Knowledge Graph."""
from __future__ import annotations

import re
from datetime import datetime, timezone


class SearchService:
    """Multi-strategy search combining exact, fuzzy, and contextual matching."""

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

    def search_entities(self, tenant: str, query: str, entity_type: str = "", provider: str = "", limit: int = 50) -> list[dict]:
        # Use entity_service.search_entities which already does scored search
        return self.entity_svc.search_entities(tenant, query, entity_type=entity_type, provider=provider, limit=limit)

    def search_relationships(self, tenant: str, source_entity_id: str = "", target_entity_id: str = "", relationship_type: str = "", limit: int = 50) -> list[dict]:
        return self.relationship_svc.list_relationships(
            tenant=tenant, source_entity_id=source_entity_id,
            target_entity_id=target_entity_id, relationship_type=relationship_type,
            limit=limit,
        )

    def search_paths(self, tenant: str, source_id: str, target_id: str, max_depth: int = 5) -> list[dict]:
        path = self.relationship_svc.find_path(source_id, target_id, max_depth=max_depth)
        return [path] if path else []

    def get_entity_context(self, entity_id: str, depth: int = 2) -> dict:
        entity = self.entity_svc.get_entity(entity_id)
        if not entity:
            return {"error": "entity not found"}
        neighborhood = self.relationship_svc.get_entity_neighborhood(entity_id, depth=depth)
        rels = self.relationship_svc.get_relationships_for_entity(entity_id, direction="both", limit=200)
        evidence: list[dict] = []
        for r in rels:
            for ev in r.get("evidence", []):
                evidence.append({**ev, "relationship_id": r["id"], "relationship_type": r["relationship_type"]})
        return {"entity": entity, "neighbors": neighborhood.get("nodes", []), "edges": neighborhood.get("edges", []), "relationships": rels, "evidence": evidence}

    def get_dependency_tree(self, entity_id: str, depth: int = 3) -> dict:
        entity = self.entity_svc.get_entity(entity_id)
        if not entity:
            return {"error": "entity not found"}
        dep_types = {"DEPENDS_ON", "IMPORTS", "CALLS", "REQUIRES"}
        tree = {"entity_id": entity_id, "name": entity["name"], "entity_type": entity["entity_type"], "dependencies": []}
        visited: set[str] = {entity_id}
        queue = [(entity_id, 0)]
        while queue:
            current_id, d = queue.pop(0)
            if d >= depth:
                continue
            for r in self.relationship_svc.get_relationships_for_entity(current_id, direction="outgoing"):
                if r["relationship_type"] not in dep_types:
                    continue
                target_id = r["target_entity_id"]
                if target_id in visited:
                    continue
                visited.add(target_id)
                target = self.entity_svc.get_entity(target_id)
                tree["dependencies"].append({
                    "entity_id": target_id,
                    "name": target["name"] if target else target_id,
                    "entity_type": target["entity_type"] if target else "unknown",
                    "relationship_type": r["relationship_type"],
                    "depth": d + 1,
                })
                queue.append((target_id, d + 1))
        return tree

    def get_impact_graph(self, entity_id: str, change_type: str = "modification", max_depth: int = 3) -> dict:
        entity = self.entity_svc.get_entity(entity_id)
        if not entity:
            return {"error": "entity not found"}
        affected: list[dict] = []
        visited: set[str] = {entity_id}
        queue = [(entity_id, 0)]
        while queue:
            current_id, d = queue.pop(0)
            if d >= max_depth:
                continue
            for r in self.relationship_svc.get_relationships_for_entity(current_id, direction="incoming"):
                target_id = r["source_entity_id"]
                if target_id in visited:
                    continue
                visited.add(target_id)
                target = self.entity_svc.get_entity(target_id)
                affected.append({
                    "entity_id": target_id,
                    "name": target["name"] if target else target_id,
                    "entity_type": target["entity_type"] if target else "unknown",
                    "relationship_type": r["relationship_type"],
                    "depth": d + 1,
                    "change_type": change_type,
                })
                queue.append((target_id, d + 1))
        return {"entity_id": entity_id, "change_type": change_type, "affected": affected, "total_affected": len(affected)}

    def natural_language_query(self, tenant: str, question: str) -> dict:
        q = question.lower().strip()
        # Try entity lookup first
        entities = self.entity_svc.search_entities(tenant, question, limit=5)
        entity_ids = [e["id"] for e in entities[:3]]
        relationships: list[dict] = []
        evidence: list[dict] = []
        answer = ""
        if "who owns" in q or "owner" in q:
            for eid in entity_ids:
                rels = self.relationship_svc.get_relationships_for_entity(eid, direction="incoming")
                owner_rels = [r for r in rels if r["relationship_type"] in ("OWNS", "MAINTAINS", "MEMBER_OF")]
                relationships.extend(owner_rels)
            answer = f"Found {len(relationships)} ownership relationships for entities matching '{question}'"
        elif "depends on" in q or "dependencies" in q or "depend" in q:
            for eid in entity_ids:
                rels = self.relationship_svc.get_relationships_for_entity(eid, direction="outgoing")
                dep_rels = [r for r in rels if r["relationship_type"] in ("DEPENDS_ON", "IMPORTS", "CALLS")]
                relationships.extend(dep_rels)
            answer = f"Found {len(relationships)} dependency relationships"
        elif "what uses" in q or "who uses" in q:
            for eid in entity_ids:
                rels = self.relationship_svc.get_relationships_for_entity(eid, direction="incoming")
                use_rels = [r for r in rels if r["relationship_type"] == "USES"]
                relationships.extend(use_rels)
            answer = f"Found {len(relationships)} usage relationships"
        elif "find path" in q or "path from" in q:
            if len(entity_ids) >= 2:
                path = self.relationship_svc.find_path(entity_ids[0], entity_ids[1])
                if path:
                    relationships = [path]
                    answer = f"Found path with {len(path)} hops"
                else:
                    answer = "No path found between the matched entities"
            else:
                answer = "Could not identify two entities for path finding"
        elif "deploy" in q:
            for eid in entity_ids:
                rels = self.relationship_svc.get_relationships_for_entity(eid, direction="both")
                deploy_rels = [r for r in rels if r["relationship_type"] in ("DEPLOYS", "BUILDS", "RUNS_ON")]
                relationships.extend(deploy_rels)
            answer = f"Found {len(relationships)} deployment relationships"
        else:
            for eid in entity_ids:
                rels = self.relationship_svc.get_relationships_for_entity(eid, direction="both", limit=10)
                relationships.extend(rels)
            answer = f"Found {len(entities)} matching entities and {len(relationships)} relationships"
        return {"answer": answer, "entities": entities, "relationships": relationships, "evidence": evidence}


search_service = SearchService()
