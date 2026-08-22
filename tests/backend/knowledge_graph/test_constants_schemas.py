"""Constants, schemas, config, indexing tests (Volume 51)."""
import pytest
from app.knowledge_graph.constants import (
    EntityType, RelationshipType, Confidence, OwnershipType,
    EvidenceSource, GraphTraversalType, EntityStatus,
    TemporalMode, SyncStatus, QualityIssueType, IngestionSource,
    DEFAULT_TENANT, MAXTraversalDepth, DEFAULTTraversalDepth,
)
from app.knowledge_graph.schemas import (
    EntityCreate, RelationshipCreate, EntitySearch, PathQuery,
    TraversalQuery, ImpactQuery, QualityQuery, GraphDashboardQuery,
)
from app.knowledge_graph.config import KnowledgeGraphConfig, get_config
from app.knowledge_graph.entity_service import EntityService
from app.knowledge_graph.relationship_service import RelationshipService
from app.knowledge_graph.indexing_service import IndexingService
from app.knowledge_graph.neo4j_service import Neo4jService


class TestConstants:
    def test_entity_type_enum(self):
        assert EntityType.SERVICE.value == "service"
        assert EntityType.REPOSITORY.value == "repository"
        assert EntityType.INCIDENT.value == "incident"
        assert len(EntityType) == 20

    def test_relationship_type_enum(self):
        assert RelationshipType.DEPENDS_ON.value == "DEPENDS_ON"
        assert RelationshipType.CALLS.value == "CALLS"
        assert len(RelationshipType) == 10

    def test_confidence_enum(self):
        assert Confidence.CONFIRMED.value == "CONFIRMED"
        assert Confidence.PROBABLE.value == "PROBABLE"

    def test_defaults(self):
        assert DEFAULT_TENANT == "default"
        assert MAXTraversalDepth == 10
        assert DEFAULTTraversalDepth == 3


class TestSchemas:
    def test_entity_create(self):
        s = EntityCreate(tenant="t", entity_type="service", name="svc")
        assert s.tenant == "t"
        assert s.name == "svc"

    def test_relationship_create(self):
        s = RelationshipCreate(source_entity_id="a", target_entity_id="b", relationship_type="DEPENDS_ON")
        assert s.confidence == "confirmed"

    def test_entity_search(self):
        s = EntitySearch(query="test")
        assert s.tenant == "default"
        assert s.limit == 50

    def test_path_query(self):
        s = PathQuery(source_entity_id="a", target_entity_id="b")
        assert s.max_depth == 5

    def test_traversal_query(self):
        s = TraversalQuery(start_id="a")
        assert s.direction == "outgoing"
        assert s.max_depth == 3

    def test_impact_query(self):
        s = ImpactQuery(entity_id="a")
        assert s.change_type == "modification"

    def test_quality_query(self):
        s = QualityQuery()
        assert s.tenant == "default"

    def test_dashboard_query(self):
        s = GraphDashboardQuery()
        assert s.include_quality is True


class TestConfig:
    def test_get_config(self):
        cfg = get_config()
        assert isinstance(cfg, KnowledgeGraphConfig)

    def test_config_defaults(self):
        cfg = KnowledgeGraphConfig()
        assert cfg.default_tenant == "default"
        assert cfg.max_traversal_depth == 10
        assert cfg.neo4j_uri == ""


class TestIndexingService:
    def test_ingest_manual(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.ingest_manual("t", [
            {"name": "svc-a", "entity_type": "service"},
            {"name": "svc-b", "entity_type": "service"},
        ], [
            {"source_name": "svc-a", "target_name": "svc-b", "relationship_type": "DEPENDS_ON"},
        ])
        assert result["entities_created"] == 2
        assert result["relationships_created"] == 1

    def test_ingest_from_repository(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.ingest_from_repository_index("t", {
            "name": "my-repo", "branch": "main",
            "files": ["src/app.py", "tests/test_app.py"],
        })
        assert result["entities_created"] >= 1

    def test_ingest_from_deployment(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.ingest_from_deployment("t", {
            "service": "svc-a", "environment": "prod",
            "commit": "abc123",
        })
        assert result["entities_created"] >= 1

    def test_ingest_from_incident(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.ingest_from_incident("t", {
            "title": "Outage", "service": "svc-a",
            "severity": "critical",
        })
        assert result["entities_created"] >= 1

    def test_ingest_from_security(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.ingest_from_security_finding("t", {
            "title": "CVE-2024-0001", "severity": "high",
            "file": "src/vuln.py",
        })
        assert result["entities_created"] >= 1

    def test_ingest_from_marketplace(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.ingest_from_marketplace("t", {
            "name": "plugin-a", "version": "1.0.0",
            "dependencies": ["dep-1"],
        })
        assert result["entities_created"] >= 1

    def test_get_sync_status(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        status = idx.get_sync_status("t")
        assert "total_syncs" in status

    def test_full_rebuild(self):
        esvc = EntityService()
        rsvc = RelationshipService()
        idx = IndexingService(esvc, rsvc)
        result = idx.full_rebuild("t")
        assert "entities_created" in result


class TestNeo4jService:
    def test_not_connected(self):
        svc = Neo4jService()
        assert svc.is_connected() is False

    def test_close_no_driver(self):
        svc = Neo4jService()
        svc.close()
        assert svc.is_connected() is False
