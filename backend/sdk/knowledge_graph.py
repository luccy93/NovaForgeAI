"""NovaForge Knowledge Graph Platform -- SDK (Volume 51)."""
from __future__ import annotations
from typing import Optional


class KnowledgeGraphMixin:
    """Sync SDK methods for the Knowledge Graph Platform."""

    def create_entity(self, tenant: str, entity_type: str, name: str, **kw) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/entities", json={"tenant": tenant, "entity_type": entity_type, "name": name, **kw})

    def list_entities(self, tenant: str = "", entity_type: str = "", limit: int = 100) -> list:
        p = {"limit": limit}
        if tenant: p["tenant"] = tenant
        if entity_type: p["entity_type"] = entity_type
        return self._request("GET", "/api/v1/knowledge-graph/entities", params=p)

    def get_entity_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/entities/stats", params={"tenant": tenant} if tenant else {})

    def search_entities(self, tenant: str, query: str, limit: int = 50) -> list:
        return self._request("GET", "/api/v1/knowledge-graph/entities/search", params={"tenant": tenant, "q": query, "limit": limit})

    def get_entity(self, entity_id: str) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}")

    def update_entity(self, entity_id: str, **kw) -> dict:
        return self._request("PUT", f"/api/v1/knowledge-graph/entities/{entity_id}", json=kw)

    def delete_entity(self, entity_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/knowledge-graph/entities/{entity_id}")

    def bulk_create_entities(self, tenant: str, entities: list[dict]) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/entities/bulk", json={"tenant": tenant, "entities": entities})

    def merge_entities(self, entity_ids: list[str], merge_into: str = "") -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/entities/merge", json={"entity_ids": entity_ids, "merge_into": merge_into})

    def list_entity_aliases(self, entity_id: str) -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/aliases")

    def add_alias(self, entity_id: str, alias_type: str, alias_value: str, source: str = "") -> dict:
        return self._request("POST", f"/api/v1/knowledge-graph/entities/{entity_id}/aliases", json={"alias_type": alias_type, "alias_value": alias_value, "source": source})

    def remove_alias(self, entity_id: str, alias_type: str, alias_value: str) -> dict:
        return self._request("DELETE", f"/api/v1/knowledge-graph/entities/{entity_id}/aliases", json={"alias_type": alias_type, "alias_value": alias_value})

    def get_entity_history(self, entity_id: str) -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/history")

    def get_entity_context(self, entity_id: str, depth: int = 2) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/context", params={"depth": depth})

    def get_dependency_tree(self, entity_id: str, depth: int = 3) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/dependencies", params={"depth": depth})

    def get_impact_graph(self, entity_id: str, change_type: str = "modification", max_depth: int = 3) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/impact", params={"change_type": change_type, "max_depth": max_depth})

    def create_relationship(self, tenant: str, source: str, target: str, rel_type: str, **kw) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/relationships", json={"tenant": tenant, "source_entity_id": source, "target_entity_id": target, "relationship_type": rel_type, **kw})

    def list_relationships(self, tenant: str = "", limit: int = 100) -> list:
        p = {"limit": limit}
        if tenant: p["tenant"] = tenant
        return self._request("GET", "/api/v1/knowledge-graph/relationships", params=p)

    def get_relationship_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/relationships/stats", params={"tenant": tenant} if tenant else {})

    def get_relationship(self, rel_id: str) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/relationships/{rel_id}")

    def update_relationship(self, rel_id: str, **kw) -> dict:
        return self._request("PUT", f"/api/v1/knowledge-graph/relationships/{rel_id}", json=kw)

    def delete_relationship(self, rel_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/knowledge-graph/relationships/{rel_id}")

    def bulk_create_relationships(self, tenant: str, relationships: list[dict]) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/relationships/bulk", json={"tenant": tenant, "relationships": relationships})

    def get_relationship_evidence(self, rel_id: str) -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/relationships/{rel_id}/evidence")

    def add_evidence(self, rel_id: str, evidence_source: str, evidence_data: dict, actor: str = "") -> dict:
        return self._request("POST", f"/api/v1/knowledge-graph/relationships/{rel_id}/evidence", json={"evidence_source": evidence_source, "evidence_data": evidence_data, "actor": actor})

    def search_entities_advanced(self, tenant: str, query: str, entity_type: str = "", limit: int = 50) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/search/entities", json={"tenant": tenant, "query": query, "entity_type": entity_type, "limit": limit})

    def search_paths(self, source_id: str, target_id: str, max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/search/paths", json={"source_id": source_id, "target_id": target_id, "max_depth": max_depth})

    def natural_language_query(self, tenant: str, question: str) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/search/natural-language", json={"tenant": tenant, "question": question})

    def bfs(self, start_id: str, direction: str = "outgoing", max_depth: int = 3, limit: int = 100) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/bfs", json={"start_id": start_id, "direction": direction, "max_depth": max_depth, "limit": limit})

    def dfs(self, start_id: str, direction: str = "outgoing", max_depth: int = 3, limit: int = 100) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/dfs", json={"start_id": start_id, "direction": direction, "max_depth": max_depth, "limit": limit})

    def shortest_path(self, source_id: str, target_id: str, max_depth: int = 10) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/shortest-path", json={"source_id": source_id, "target_id": target_id, "max_depth": max_depth})

    def all_paths(self, source_id: str, target_id: str, max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/all-paths", json={"source_id": source_id, "target_id": target_id, "max_depth": max_depth})

    def blast_radius(self, entity_id: str, change_type: str = "modification", max_depth: int = 5) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/blast-radius", json={"entity_id": entity_id, "change_type": change_type, "max_depth": max_depth})

    def dependency_path(self, entity_id: str, direction: str = "upstream", max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/dependency-path", json={"entity_id": entity_id, "direction": direction, "max_depth": max_depth})

    def ownership_path(self, entity_id: str, max_depth: int = 3) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/ownership-path", json={"entity_id": entity_id, "max_depth": max_depth})

    def deployment_path(self, entity_id: str, max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/deployment-path", json={"entity_id": entity_id, "max_depth": max_depth})

    def incident_path(self, entity_id: str, max_depth: int = 3) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/incident-path", json={"entity_id": entity_id, "max_depth": max_depth})

    def get_connected_components(self) -> list:
        return self._request("GET", "/api/v1/knowledge-graph/traverse/connected-components")

    def detect_cycles(self, tenant: str = "") -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/cycles", json={"tenant": tenant})

    def get_communities(self) -> list:
        return self._request("GET", "/api/v1/knowledge-graph/traverse/communities")

    def get_degree_centrality(self, tenant: str = "", entity_type: str = "") -> list:
        p = {}
        if tenant: p["tenant"] = tenant
        if entity_type: p["entity_type"] = entity_type
        return self._request("GET", "/api/v1/knowledge-graph/traverse/centrality", params=p)

    def detect_duplicates(self, tenant: str = "", entity_type: str = "", threshold: float = 0.85) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/resolution/detect", json={"tenant": tenant, "entity_type": entity_type, "threshold": threshold})

    def resolve_entities(self, tenant: str, entity_ids: list[str], merge_into: str = "") -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/resolution/resolve", json={"tenant": tenant, "entity_ids": entity_ids, "merge_into": merge_into})

    def auto_resolve(self, tenant: str, entity_type: str = "", threshold: float = 0.9) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/resolution/auto-resolve", json={"tenant": tenant, "entity_type": entity_type, "threshold": threshold})

    def get_resolution_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/resolution/stats", params={"tenant": tenant} if tenant else {})

    def get_ownership_at_time(self, entity_id: str, timestamp: str = "", tenant: str = "default") -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/temporal/{entity_id}/ownership", params={"timestamp": timestamp, "tenant": tenant})

    def get_deployments_at_time(self, entity_id: str, timestamp: str = "", tenant: str = "default") -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/temporal/{entity_id}/deployments", params={"timestamp": timestamp, "tenant": tenant})

    def create_snapshot(self, tenant: str, name: str, description: str = "", snapshot_type: str = "manual") -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/temporal/snapshots", json={"tenant": tenant, "name": name, "description": description, "snapshot_type": snapshot_type})

    def get_snapshot(self, tenant: str = "default", name: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/temporal/snapshots", params={"tenant": tenant, "name": name})

    def validate_temporal_consistency(self, tenant: str = "") -> list:
        return self._request("GET", "/api/v1/knowledge-graph/temporal/consistency", params={"tenant": tenant} if tenant else {})

    def get_quality_metrics(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/quality/metrics", params={"tenant": tenant} if tenant else {})

    def get_health_score(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/quality/health-score", params={"tenant": tenant} if tenant else {})

    def get_quality_report(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/quality/report", params={"tenant": tenant} if tenant else {})

    def get_graph_health(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health", params={"tenant": tenant} if tenant else {})

    def get_graph_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/stats", params={"tenant": tenant} if tenant else {})

    def get_query_performance(self) -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/performance")

    def get_graph_summary(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/summary", params={"tenant": tenant} if tenant else {})

    def check_neo4j_health(self) -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/neo4j")

    def get_health_alerts(self, tenant: str = "") -> list:
        return self._request("GET", "/api/v1/knowledge-graph/health/alerts", params={"tenant": tenant} if tenant else {})

    def ingest_from_repository(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/repository", json={"tenant": tenant, "data": data})

    def ingest_from_deployment(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/deployment", json={"tenant": tenant, "data": data})

    def ingest_from_incident(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/incident", json={"tenant": tenant, "data": data})

    def ingest_from_security(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/security", json={"tenant": tenant, "data": data})

    def ingest_from_marketplace(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/marketplace", json={"tenant": tenant, "data": data})

    def ingest_manual(self, tenant: str, entities: list[dict]) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/manual", json={"tenant": tenant, "entities": entities})

    def get_ingestion_status(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/ingest/status", params={"tenant": tenant} if tenant else {})
