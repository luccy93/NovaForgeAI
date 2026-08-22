"""EntityResolutionService, TemporalService, EvidenceService tests (Volume 51)."""
import pytest
from app.knowledge_graph.entity_service import EntityService
from app.knowledge_graph.relationship_service import RelationshipService
from app.knowledge_graph.entity_resolution_service import EntityResolutionService
from app.knowledge_graph.temporal_service import TemporalService
from app.knowledge_graph.evidence_service import EvidenceService


@pytest.fixture()
def esvc():
    return EntityService()


@pytest.fixture()
def rsvc():
    return RelationshipService()


@pytest.fixture()
def res(esvc, rsvc):
    return EntityResolutionService(esvc, rsvc)


@pytest.fixture()
def temporal(esvc, rsvc):
    return TemporalService(esvc, rsvc)


@pytest.fixture()
def evidence(esvc, rsvc):
    return EvidenceService(esvc, rsvc)


class TestEntityResolution:
    def test_find_duplicates_found(self, res, esvc):
        esvc.create_entity("t", "service", "payment-api")
        esvc.create_entity("t", "service", "payment-api-v2")
        dupes = res.find_duplicates("t", threshold=0.5)
        assert len(dupes) >= 1
        assert dupes[0]["similarity"] >= 0.5

    def test_find_duplicates_none(self, res, esvc):
        esvc.create_entity("t", "service", "completely-different")
        dupes = res.find_duplicates("t", threshold=0.99)
        assert dupes == []

    def test_resolve_entities(self, res, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "svc-a")
        e2 = esvc.create_entity("t", "service", "svc-a-copy")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        result = res.resolve_entities("t", [e1["id"], e2["id"]])
        assert "merged_into" in result
        assert result["entities_merged"] == 1

    def test_resolve_not_enough(self, res):
        assert "error" in res.resolve_entities("t", ["x"])

    def test_find_canonical_id(self, res, esvc):
        esvc.create_entity("t", "service", "svc", external_id="ext-1", provider="github")
        cid = res.find_canonical_id("t", "ext-1", "github")
        assert cid is not None

    def test_compute_similarity(self, res):
        assert res._compute_similarity("abc", "abc") == 1.0
        assert res._compute_similarity("abc", "xyz") < 0.5
        assert res._compute_similarity("", "abc") == 0.0

    def test_get_resolution_stats(self, res, esvc):
        esvc.create_entity("t", "service", "svc-a")
        stats = res.get_resolution_stats("t")
        assert stats["total_entities"] == 1


class TestTemporalService:
    def test_create_snapshot(self, temporal, esvc, rsvc):
        esvc.create_entity("t", "service", "svc")
        snap = temporal.create_snapshot("t", "snap-1")
        assert snap["name"] == "snap-1"
        assert snap["entity_count"] == 1

    def test_get_snapshot_data(self, temporal, esvc):
        esvc.create_entity("t", "service", "svc")
        temporal.create_snapshot("t", "snap-1")
        data = temporal.get_snapshot_data("t", "snap-1")
        assert data is not None
        assert data["name"] == "snap-1"

    def test_get_snapshot_not_found(self, temporal):
        assert temporal.get_snapshot_data("t", "nonexistent") is None

    def test_get_entity_history(self, temporal, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        history = temporal.get_entity_history(e1["id"])
        assert len(history) >= 1

    def test_validate_consistency(self, temporal, esvc):
        issues = temporal.validate_temporal_consistency("t")
        assert isinstance(issues, list)

    def test_expire_relationship(self, temporal, rsvc):
        e1 = {"id": "a"}
        e2 = {"id": "b"}
        r = rsvc.create_relationship("t", "a", "b", "DEPENDS_ON")
        assert temporal.expire_relationship(r["id"]) is True


class TestEvidenceService:
    def test_add_evidence(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        ev = evidence.add_evidence(r["id"], "git", {"file": "CODEOWNERS"}, actor="bot")
        assert ev["source"] == "git"

    def test_get_evidence(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        evidence.add_evidence(r["id"], "git", {"file": "f"})
        evs = evidence.get_evidence(r["id"])
        assert len(evs) == 1

    def test_validate_evidence(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        result = evidence.validate_evidence(r["id"])
        assert result["has_evidence"] is False
        evidence.add_evidence(r["id"], "git", {"f": 1})
        result = evidence.validate_evidence(r["id"])
        assert result["has_evidence"] is True
        assert result["evidence_count"] == 1

    def test_get_entity_provenance(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        evidence.add_evidence(r["id"], "git", {"f": 1})
        prov = evidence.get_entity_provenance(e1["id"])
        assert prov["evidence_count"] == 1

    def test_verify_integrity(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        missing = evidence.verify_evidence_integrity("t")
        assert len(missing) == 1

    def test_get_evidence_summary(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        evidence.add_evidence(r["id"], "git", {"f": 1})
        summary = evidence.get_evidence_summary("t")
        assert summary["total_relationships"] == 1
        assert summary["with_evidence"] == 1

    def test_get_audit_trail(self, evidence, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        r = rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        evidence.add_evidence(r["id"], "git", {"f": 1}, actor="bot")
        trail = evidence.get_audit_trail("t")
        assert len(trail) >= 1
