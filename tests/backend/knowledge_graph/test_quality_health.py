"""QualityService and HealthService tests (Volume 51)."""
import pytest
from app.knowledge_graph.entity_service import EntityService
from app.knowledge_graph.relationship_service import RelationshipService
from app.knowledge_graph.evidence_service import EvidenceService
from app.knowledge_graph.quality_service import QualityService
from app.knowledge_graph.health_service import HealthService


@pytest.fixture()
def esvc():
    return EntityService()


@pytest.fixture()
def rsvc():
    return RelationshipService()


@pytest.fixture()
def evc(esvc, rsvc):
    return EvidenceService(esvc, rsvc)


@pytest.fixture()
def qsvc(esvc, rsvc, evc):
    return QualityService(esvc, rsvc, evc)


@pytest.fixture()
def hsvc(esvc, rsvc, qsvc):
    return HealthService(esvc, rsvc, None, qsvc)


class TestQualityMetrics:
    def test_compute(self, qsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        metrics = qsvc.compute_quality_metrics("t")
        assert metrics["entity_count"] == 2
        assert metrics["relationship_count"] == 1

    def test_detect_orphans(self, qsvc, esvc):
        esvc.create_entity("t", "service", "orphan")
        orphans = qsvc.detect_orphan_nodes("t")
        assert len(orphans) == 1
        assert orphans[0]["name"] == "orphan"

    def test_no_orphans(self, qsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        assert qsvc.detect_orphan_nodes("t") == []

    def test_detect_stale(self, qsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        rsvc.update_relationship(r["id"], observed_at="2020-01-01T00:00:00Z")
        stale = qsvc.detect_stale_relationships("t", stale_days=1)
        assert len(stale) >= 1

    def test_detect_missing_evidence(self, qsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        missing = qsvc.detect_missing_evidence("t")
        assert len(missing) == 1

    def test_detect_invalid_edges(self, qsvc, rsvc):
        rsvc.create_relationship("t", "nonexistent-a", "nonexistent-b", "DEPENDS_ON")
        invalid = qsvc.detect_invalid_edges("t")
        assert len(invalid) == 1

    def test_get_health_score(self, qsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        score = qsvc.get_health_score("t")
        assert "score" in score
        assert 0 <= score["score"] <= 100

    def test_get_quality_report(self, qsvc, esvc):
        esvc.create_entity("t", "service", "svc")
        report = qsvc.get_quality_report("t")
        assert "health_score" in report
        assert "orphan_nodes" in report

    def test_record_metric(self, qsvc):
        m = qsvc.record_metric("t", "test.metric", 42.0)
        assert m["metric_name"] == "test.metric"
        assert m["metric_value"] == 42.0

    def test_get_metric_history(self, qsvc):
        qsvc.record_metric("t", "m1", 1.0)
        qsvc.record_metric("t", "m1", 2.0)
        history = qsvc.get_metric_history("t", "m1")
        assert len(history) == 2

    def test_auto_fix_dry_run(self, qsvc, esvc):
        esvc.create_entity("t", "service", "orphan")
        fixes = qsvc.auto_fix("t", dry_run=True)
        assert "fixes_suggested" in fixes

    def test_detect_cycles(self, qsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        rsvc.create_relationship("t", e2["id"], e1["id"], "DEPENDS_ON")
        cycles = qsvc.detect_cycles("t")
        assert len(cycles) >= 1

    def test_detect_duplicates(self, qsvc, esvc):
        esvc.create_entity("t", "service", "payment-api")
        esvc.create_entity("t", "service", "payment-api-v2")
        dupes = qsvc.detect_duplicate_entities("t", threshold=0.5)
        assert len(dupes) >= 1


class TestHealthService:
    def test_get_health(self, hsvc, esvc):
        esvc.create_entity("t", "service", "svc")
        h = hsvc.get_health("t")
        assert h["status"] in ("healthy", "degraded", "critical")
        assert h["node_count"] == 1

    def test_get_stats(self, hsvc, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        stats = hsvc.get_stats("t")
        assert stats["total_entities"] == 2
        assert stats["total_relationships"] == 1

    def test_get_query_performance(self, hsvc):
        perf = hsvc.get_query_performance()
        assert "total_queries" in perf

    def test_record_query_latency(self, hsvc):
        hsvc.record_query_latency("search", 10.5)
        hsvc.record_query_latency("traversal", 20.3)
        perf = hsvc.get_query_performance()
        assert perf["total_queries"] == 2
        assert perf["avg_search_ms"] == 10.5

    def test_check_consistency(self, hsvc, esvc):
        esvc.create_entity("t", "service", "orphan")
        result = hsvc.check_consistency("t")
        assert "orphan_nodes" in result
        assert result["orphan_nodes"] >= 1

    def test_get_graph_summary(self, hsvc, esvc):
        esvc.create_entity("t", "service", "svc")
        summary = hsvc.get_graph_summary("t")
        assert "summary" in summary
        assert "total_entities" in summary

    def test_check_neo4j_health(self, hsvc):
        result = hsvc.check_neo4j_health()
        assert result["connected"] is False

    def test_get_alerts(self, hsvc):
        alerts = hsvc.get_alerts("t")
        assert isinstance(alerts, list)

    def test_reset_stats(self, hsvc):
        hsvc.record_query_latency("search", 10.0)
        hsvc.reset_stats()
        perf = hsvc.get_query_performance()
        assert perf["total_queries"] == 0

    def test_get_ingestion_stats(self, hsvc):
        stats = hsvc.get_ingestion_stats("t")
        assert "total_syncs" in stats
