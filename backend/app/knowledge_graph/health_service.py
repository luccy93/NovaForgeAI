"""Graph health monitoring and operational status."""
from __future__ import annotations

import time
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HealthService:
    def __init__(self, entity_service=None, relationship_service=None, neo4j_service=None, quality_service=None):
        self._entity_svc = entity_service
        self._relationship_svc = relationship_service
        self._neo4j_svc = neo4j_service
        self._quality_svc = quality_service
        self._query_latencies: list[dict] = []
        self._alert_history: list[dict] = []

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

    @property
    def quality_svc(self):
        if self._quality_svc is None:
            from app.knowledge_graph.quality_service import quality_service
            self._quality_svc = quality_service
        return self._quality_svc

    def get_health(self, tenant: str = "") -> dict:
        stats = self.get_stats(tenant)
        node_count = stats.get("total_entities", 0)
        edge_count = stats.get("total_relationships", 0)
        issues: list[str] = []
        if node_count == 0:
            issues.append("No entities in graph")
        if edge_count == 0:
            issues.append("No relationships in graph")
        try:
            quality = self.quality_svc.get_health_score(tenant)
            quality_score = quality.get("score", 0)
        except Exception:
            quality_score = 50
        if quality_score < 50:
            issues.append(f"Low quality score: {quality_score}")
        status = "healthy"
        if issues:
            status = "degraded" if len(issues) <= 2 else "critical"
        return {"status": status, "node_count": node_count, "edge_count": edge_count, "quality_score": quality_score, "issues_count": len(issues), "issues": issues, "last_check": _now()}

    def get_stats(self, tenant: str = "") -> dict:
        all_entities = self.entity_svc.list_entities(tenant=tenant, limit=100000, status="active")
        all_rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=True, limit=100000)
        inactive_rels = self.relationship_svc.list_relationships(tenant=tenant, is_active=False, limit=100000)
        by_type_e: dict[str, int] = {}
        for e in all_entities:
            by_type_e[e["entity_type"]] = by_type_e.get(e["entity_type"], 0) + 1
        by_type_r: dict[str, int] = {}
        for r in all_rels:
            by_type_r[r["relationship_type"]] = by_type_r.get(r["relationship_type"], 0) + 1
        return {"total_entities": len(all_entities), "total_relationships": len(all_rels), "inactive_relationships": len(inactive_rels), "entities_by_type": by_type_e, "relationships_by_type": by_type_r}

    def get_ingestion_stats(self, tenant: str = "") -> dict:
        return {"total_syncs": 0, "last_sync": None, "sync_status": "not_configured"}

    def get_query_performance(self) -> dict:
        lats = self._query_latencies
        if not lats:
            return {"avg_search_ms": 0, "avg_traversal_ms": 0, "p95_latency_ms": 0, "total_queries": 0}
        search_lats = [l["latency_ms"] for l in lats if l["query_type"] == "search"]
        trav_lats = [l["latency_ms"] for l in lats if l["query_type"] == "traversal"]
        all_ms = sorted([l["latency_ms"] for l in lats])
        p95_idx = int(len(all_ms) * 0.95) if all_ms else 0
        return {
            "avg_search_ms": sum(search_lats) / len(search_lats) if search_lats else 0,
            "avg_traversal_ms": sum(trav_lats) / len(trav_lats) if trav_lats else 0,
            "p95_latency_ms": all_ms[min(p95_idx, len(all_ms) - 1)] if all_ms else 0,
            "total_queries": len(lats),
        }

    def check_consistency(self, tenant: str = "") -> dict:
        orphans = self.quality_svc.detect_orphan_nodes(tenant)
        invalid = self.quality_svc.detect_invalid_edges(tenant)
        missing = self.quality_svc.detect_missing_evidence(tenant)
        stale = self.quality_svc.detect_stale_relationships(tenant)
        return {"orphan_nodes": len(orphans), "invalid_edges": len(invalid), "missing_evidence": len(missing), "stale_relationships": len(stale), "total_issues": len(orphans) + len(invalid) + len(missing) + len(stale)}

    def get_graph_summary(self, tenant: str = "") -> dict:
        stats = self.get_stats(tenant)
        return {"summary": f"Knowledge graph contains {stats['total_entities']} entities and {stats['total_relationships']} relationships across {len(stats['entities_by_type'])} entity types and {len(stats['relationships_by_type'])} relationship types.", **stats}

    def check_neo4j_health(self) -> dict:
        return {"connected": False, "message": "Neo4j integration available when configured"}

    def record_query_latency(self, query_type: str, latency_ms: float) -> None:
        self._query_latencies.append({"query_type": query_type, "latency_ms": latency_ms, "timestamp": _now()})
        if len(self._query_latencies) > 10000:
            self._query_latencies = self._query_latencies[-5000:]

    def get_alerts(self, tenant: str = "") -> list[dict]:
        alerts: list[dict] = []
        try:
            health = self.get_health(tenant)
            if health["status"] != "healthy":
                alerts.append({"level": "warning" if health["status"] == "degraded" else "critical", "message": f"Graph health: {health['status']}", "timestamp": _now()})
        except Exception:
            pass
        return alerts

    def reset_stats(self) -> None:
        self._query_latencies.clear()
        self._alert_history.clear()


health_service = HealthService()
