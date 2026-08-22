"""RelationshipService tests (Volume 51)."""
import pytest
from app.knowledge_graph.entity_service import EntityService
from app.knowledge_graph.relationship_service import RelationshipService


@pytest.fixture()
def esvc():
    return EntityService()


@pytest.fixture()
def rsvc():
    return RelationshipService()


@pytest.fixture()
def pair(esvc):
    e1 = esvc.create_entity("t", "service", "svc-a")
    e2 = esvc.create_entity("t", "service", "svc-b")
    return e1["id"], e2["id"]


class TestRelationshipCRUD:
    def test_create(self, rsvc, pair):
        r = rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        assert r["id"]
        assert r["relationship_type"] == "DEPENDS_ON"
        assert r["is_active"] is True

    def test_get(self, rsvc, pair):
        r = rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        got = rsvc.get_relationship(r["id"])
        assert got["id"] == r["id"]

    def test_get_not_found(self, rsvc):
        assert rsvc.get_relationship("x") is None

    def test_update(self, rsvc, pair):
        r = rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        updated = rsvc.update_relationship(r["id"], confidence="probable")
        assert updated["confidence"] == "probable"
        assert updated["version"] == 2

    def test_delete(self, rsvc, pair):
        r = rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        assert rsvc.delete_relationship(r["id"]) is True
        assert rsvc.get_relationship(r["id"])["is_active"] is False

    def test_delete_not_found(self, rsvc):
        assert rsvc.delete_relationship("x") is False


class TestRelationshipQuery:
    def test_list_empty(self, rsvc):
        assert rsvc.list_relationships("t") == []

    def test_list_by_source(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        r = rsvc.list_relationships("t", source_entity_id=pair[0])
        assert len(r) == 1

    def test_list_by_type(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        rsvc.create_relationship("t", pair[0], pair[1], "CALLS")
        assert len(rsvc.list_relationships("t", relationship_type="DEPENDS_ON")) == 1

    def test_get_for_entity_outgoing(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        rels = rsvc.get_relationships_for_entity(pair[0], direction="outgoing")
        assert len(rels) == 1
        assert rels[0]["source_entity_id"] == pair[0]

    def test_get_for_entity_incoming(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        rels = rsvc.get_relationships_for_entity(pair[1], direction="incoming")
        assert len(rels) == 1

    def test_get_for_entity_both(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        rels = rsvc.get_relationships_for_entity(pair[0], direction="both")
        assert len(rels) == 1


class TestTraversal:
    def test_find_path_direct(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        path = rsvc.find_path(pair[0], pair[1])
        assert path is not None
        assert len(path) == 2

    def test_find_path_no_path(self, rsvc, pair):
        assert rsvc.find_path(pair[0], pair[1]) is None

    def test_find_path_same_node(self, rsvc, pair):
        path = rsvc.find_path(pair[0], pair[0])
        assert path is not None
        assert len(path) == 1

    def test_find_path_max_depth(self, rsvc, esvc):
        nodes = [esvc.create_entity("t", "service", f"s{i}")["id"] for i in range(4)]
        for i in range(3):
            rsvc.create_relationship("t", nodes[i], nodes[i + 1], "DEPENDS_ON")
        assert rsvc.find_path(nodes[0], nodes[3], max_depth=2) is None
        assert rsvc.find_path(nodes[0], nodes[3], max_depth=3) is not None

    def test_get_neighbors_depth1(self, rsvc, esvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        n = rsvc.get_neighbors(e1["id"], depth=1)
        assert len(n) == 1
        assert n[0]["entity_id"] == e2["id"]

    def test_get_neighbors_depth2(self, rsvc, esvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        e3 = esvc.create_entity("t", "service", "c")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        rsvc.create_relationship("t", e2["id"], e3["id"], "DEPENDS_ON")
        n = rsvc.get_neighbors(e1["id"], depth=2)
        assert len(n) == 2


class TestBulkStats:
    def test_bulk_create(self, rsvc, pair):
        result = rsvc.bulk_create_relationships("t", [
            {"source_entity_id": pair[0], "target_entity_id": pair[1], "relationship_type": "DEPENDS_ON"},
            {"source_entity_id": pair[0], "target_entity_id": pair[1], "relationship_type": "CALLS"},
        ])
        assert result["created"] == 2

    def test_get_stats(self, rsvc, pair):
        rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        rsvc.create_relationship("t", pair[0], pair[1], "CALLS")
        stats = rsvc.get_relationship_stats("t")
        assert stats["total"] == 2
        assert stats["active"] == 2


class TestEvidence:
    def test_add_evidence(self, rsvc, pair):
        r = rsvc.create_relationship("t", pair[0], pair[1], "DEPENDS_ON")
        ev = rsvc.add_evidence(r["id"], "git", {"file": "CODEOWNERS"})
        assert ev["source"] == "git"
        assert len(rsvc.get_relationship(r["id"])["evidence"]) == 1


class TestNeighborhood:
    def test_get_neighborhood(self, rsvc, esvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        nb = rsvc.get_entity_neighborhood(e1["id"], depth=1)
        assert e1["id"] in nb["nodes"]
        assert e2["id"] in nb["nodes"]
        assert len(nb["edges"]) == 1


class TestCycles:
    def test_detect_cycles(self, rsvc, esvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        rsvc.create_relationship("t", e2["id"], e1["id"], "DEPENDS_ON")
        cycles = rsvc.detect_cycles("t")
        assert len(cycles) >= 1

    def test_no_cycles(self, rsvc, esvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        assert rsvc.detect_cycles("t") == []
