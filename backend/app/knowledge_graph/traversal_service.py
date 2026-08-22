"""Graph traversal algorithms for the Knowledge Graph."""
from __future__ import annotations

from collections import deque


class TraversalService:
    """BFS, DFS, path-finding, and graph analysis algorithms."""

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

    def bfs(self, start_id: str, direction: str = "outgoing", max_depth: int = 3, relationship_types: list[str] | None = None, limit: int = 100) -> list[dict]:
        visited: set[str] = {start_id}
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])
        results: list[dict] = []
        while queue and len(results) < limit:
            current, d = queue.popleft()
            if d >= max_depth:
                continue
            for r in self.relationship_svc.get_relationships_for_entity(current, direction=direction):
                if relationship_types and r["relationship_type"] not in relationship_types:
                    continue
                neighbor = r["target_entity_id"] if r["source_entity_id"] == current else r["source_entity_id"]
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                entity = self.entity_svc.get_entity(neighbor)
                results.append({
                    "entity_id": neighbor,
                    "entity_type": entity["entity_type"] if entity else "unknown",
                    "name": entity["name"] if entity else neighbor,
                    "depth": d + 1,
                    "via_relationship": r["relationship_type"],
                })
                queue.append((neighbor, d + 1))
        return results

    def dfs(self, start_id: str, direction: str = "outgoing", max_depth: int = 3, relationship_types: list[str] | None = None, limit: int = 100) -> list[dict]:
        visited: set[str] = set()
        results: list[dict] = []

        def _dfs(node_id: str, depth: int) -> None:
            if len(results) >= limit or depth >= max_depth or node_id in visited:
                return
            visited.add(node_id)
            for r in self.relationship_svc.get_relationships_for_entity(node_id, direction=direction):
                if relationship_types and r["relationship_type"] not in relationship_types:
                    continue
                neighbor = r["target_entity_id"] if r["source_entity_id"] == node_id else r["source_entity_id"]
                if neighbor in visited:
                    continue
                entity = self.entity_svc.get_entity(neighbor)
                results.append({
                    "entity_id": neighbor,
                    "entity_type": entity["entity_type"] if entity else "unknown",
                    "name": entity["name"] if entity else neighbor,
                    "depth": depth + 1,
                    "via_relationship": r["relationship_type"],
                })
                _dfs(neighbor, depth + 1)

        _dfs(start_id, 0)
        return results

    def shortest_path(self, source_id: str, target_id: str, relationship_types: list[str] | None = None, max_depth: int = 10) -> list[dict] | None:
        path = self.relationship_svc.find_path(source_id, target_id, max_depth=max_depth, relationship_types=relationship_types)
        if not path:
            return None
        enriched: list[dict] = []
        for step in path:
            eid = step.get("entity_id", "")
            entity = self.entity_svc.get_entity(eid) if eid else None
            enriched.append({**step, "name": entity["name"] if entity else eid, "entity_type": entity["entity_type"] if entity else ""})
        return enriched

    def all_paths(self, source_id: str, target_id: str, max_depth: int = 5, relationship_types: list[str] | None = None) -> list[list[dict]]:
        paths: list[list[dict]] = []
        visited: set[str] = set()

        def _dfs(node_id: str, path_so_far: list[dict]) -> None:
            if len(paths) >= 10:
                return
            if node_id == target_id and path_so_far:
                paths.append(list(path_so_far))
                return
            if len(path_so_far) >= max_depth:
                return
            visited.add(node_id)
            for r in self.relationship_svc.get_relationships_for_entity(node_id, direction="both"):
                if relationship_types and r["relationship_type"] not in relationship_types:
                    continue
                neighbor = r["target_entity_id"] if r["source_entity_id"] == node_id else r["source_entity_id"]
                if neighbor in visited and neighbor != target_id:
                    continue
                path_so_far.append({"entity_id": neighbor, "relationship_type": r["relationship_type"], "from_id": node_id})
                _dfs(neighbor, path_so_far)
                path_so_far.pop()
            visited.discard(node_id)

        _dfs(source_id, [])
        return paths

    def blast_radius(self, entity_id: str, change_type: str = "modification", max_depth: int = 5, entity_types: list[str] | None = None) -> dict:
        affected: list[dict] = []
        visited: set[str] = {entity_id}
        queue = [(entity_id, 0)]
        max_reached = 0
        while queue:
            current_id, d = queue.pop(0)
            if d >= max_depth:
                continue
            for r in self.relationship_svc.get_relationships_for_entity(current_id, direction="incoming"):
                target_id = r["source_entity_id"]
                if target_id in visited:
                    continue
                visited.add(target_id)
                entity = self.entity_svc.get_entity(target_id)
                if entity and entity_types and entity["entity_type"] not in entity_types:
                    continue
                affected.append({
                    "entity_id": target_id,
                    "name": entity["name"] if entity else target_id,
                    "entity_type": entity["entity_type"] if entity else "unknown",
                    "relationship_type": r["relationship_type"],
                    "depth": d + 1,
                })
                max_reached = max(max_reached, d + 1)
                queue.append((target_id, d + 1))
        return {"entity_id": entity_id, "change_type": change_type, "affected": affected, "count": len(affected), "max_depth_reached": max_reached}

    def dependency_path(self, entity_id: str, direction: str = "upstream", max_depth: int = 5) -> list[dict]:
        dep_types = {"DEPENDS_ON", "IMPORTS", "CALLS", "REQUIRES"}
        dir_ = "incoming" if direction == "upstream" else "outgoing"
        return self.bfs(entity_id, direction=dir_, max_depth=max_depth, relationship_types=list(dep_types))

    def ownership_path(self, entity_id: str, max_depth: int = 3) -> list[dict]:
        own_types = {"MEMBER_OF", "OWNS", "MAINTAINS", "APPROVES"}
        return self.bfs(entity_id, direction="both", max_depth=max_depth, relationship_types=list(own_types))

    def deployment_path(self, entity_id: str, max_depth: int = 5) -> list[dict]:
        deploy_types = {"DEPLOYS", "BUILDS", "RUNS_ON"}
        return self.bfs(entity_id, direction="both", max_depth=max_depth, relationship_types=list(deploy_types))

    def incident_path(self, entity_id: str, max_depth: int = 3) -> list[dict]:
        incident_types = {"AFFECTS", "CAUSED_BY", "TRIGGERS"}
        return self.bfs(entity_id, direction="both", max_depth=max_depth, relationship_types=list(incident_types))

    def get_connected_components(self) -> list[list[str]]:
        adj: dict[str, set[str]] = {}
        for r in self.relationship_svc.list_relationships(is_active=True, limit=10000):
            src, tgt = r["source_entity_id"], r["target_entity_id"]
            adj.setdefault(src, set()).add(tgt)
            adj.setdefault(tgt, set()).add(src)
        visited: set[str] = set()
        components: list[list[str]] = []
        for node in adj:
            if node in visited:
                continue
            component: list[str] = []
            queue = [node]
            while queue:
                n = queue.pop()
                if n in visited:
                    continue
                visited.add(n)
                component.append(n)
                queue.extend(adj.get(n, set()) - visited)
            components.append(component)
        return components

    def detect_cycles(self, tenant: str = "", relationship_types: list[str] | None = None) -> list[list[str]]:
        return self.relationship_svc.detect_cycles(tenant=tenant)

    def community_detection(self) -> list[dict]:
        components = self.get_connected_components()
        communities: list[dict] = []
        for idx, comp in enumerate(components):
            entity_type_counts: dict[str, int] = {}
            for eid in comp:
                entity = self.entity_svc.get_entity(eid)
                if entity:
                    et = entity["entity_type"]
                    entity_type_counts[et] = entity_type_counts.get(et, 0) + 1
            communities.append({
                "community_id": idx,
                "size": len(comp),
                "entity_ids": comp[:20],
                "entity_type_distribution": entity_type_counts,
            })
        return sorted(communities, key=lambda c: c["size"], reverse=True)

    def get_degree_centrality(self, tenant: str = "", entity_type: str = "") -> list[dict]:
        degrees: dict[str, int] = {}
        for r in self.relationship_svc.list_relationships(is_active=True, limit=10000):
            degrees[r["source_entity_id"]] = degrees.get(r["source_entity_id"], 0) + 1
            degrees[r["target_entity_id"]] = degrees.get(r["target_entity_id"], 0) + 1
        results: list[dict] = []
        for eid, degree in degrees.items():
            entity = self.entity_svc.get_entity(eid)
            if not entity:
                continue
            if tenant and entity["tenant"] != tenant:
                continue
            if entity_type and entity["entity_type"] != entity_type:
                continue
            results.append({"entity_id": eid, "name": entity["name"], "entity_type": entity["entity_type"], "degree": degree})
        return sorted(results, key=lambda x: x["degree"], reverse=True)


traversal_service = TraversalService()
