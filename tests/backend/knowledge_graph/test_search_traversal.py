"""SearchService and TraversalService tests (Volume 51)."""
import pytest
from app.knowledge_graph.entity_service import EntityService
from app.knowledge_graph.relationship_service import RelationshipService
from app.knowledge_graph.search_service import SearchService
from app.knowledge_graph.traversal_service import TraversalService


@pytest.fixture()
def esvc():
    return EntityService()


@pytest.fixture()
def rsvc():
    return RelationshipService()


@pytest.fixture()
def search(esvc, rsvc):
    return SearchService(esvc, rsvc)


@pytest.fixture()
def traverse(esvc, rsvc):
    return TraversalService(esvc, rsvc)


def _graph(esvc, rsvc):
    """Create a chain: a -> b -> c -> d, plus a -> c shortcut."""
    a = esvc.create_entity("t", "service", "svc-a")
    b = esvc.create_entity("t", "service", "svc-b")
    c = esvc.create_entity("t", "service", "svc-c")
    d = esvc.create_entity("t", "repository", "repo-d")
    rsvc.create_relationship("t", a["id"], b["id"], "DEPENDS_ON")
    rsvc.create_relationship("t", b["id"], c["id"], "DEPENDS_ON")
    rsvc.create_relationship("t", c["id"], d["id"], "CONTAINS")
    rsvc.create_relationship("t", a["id"], c["id"], "CALLS")
    return a, b, c, d


class TestSearchEntities:
    def test_basic(self, search, esvc):
        esvc.create_entity("t", "service", "payment-svc")
        results = search.search_entities("t", "payment")
        assert len(results) >= 1

    def test_no_match(self, search, esvc):
        esvc.create_entity("t", "service", "payment-svc")
        assert search.search_entities("t", "zzz") == []


class TestSearchPaths:
    def test_finds_path(self, search, esvc, rsvc):
        a, b, c, _ = _graph(esvc, rsvc)
        paths = search.search_paths("t", a["id"], c["id"])
        assert len(paths) >= 1

    def test_no_path(self, search, esvc, rsvc):
        a, b, _, _ = _graph(esvc, rsvc)
        e = esvc.create_entity("t", "service", "isolated")
        assert search.search_paths("t", a["id"], e["id"]) == []


class TestEntityContext:
    def test_get_context(self, search, esvc, rsvc):
        a, b, c, _ = _graph(esvc, rsvc)
        ctx = search.get_entity_context(a["id"])
        assert "entity" in ctx
        assert ctx["entity"]["name"] == "svc-a"
        assert len(ctx["neighbors"]) > 0

    def test_not_found(self, search):
        assert "error" in search.get_entity_context("x")


class TestDependencyTree:
    def test_basic(self, search, esvc, rsvc):
        a, b, c, _ = _graph(esvc, rsvc)
        tree = search.get_dependency_tree(a["id"])
        assert tree["entity_id"] == a["id"]
        assert len(tree["dependencies"]) >= 2

    def test_not_found(self, search):
        assert "error" in search.get_dependency_tree("x")


class TestImpactGraph:
    def test_basic(self, search, esvc, rsvc):
        a, b, c, d = _graph(esvc, rsvc)
        impact = search.get_impact_graph(d["id"])
        assert impact["total_affected"] >= 1

    def test_not_found(self, search):
        assert "error" in search.get_impact_graph("x")


class TestNLQuery:
    def test_ownership(self, search, esvc, rsvc):
        a, b, _, _ = _graph(esvc, rsvc)
        rsvc.create_relationship("t", b["id"], a["id"], "OWNS")
        result = search.natural_language_query("t", "who owns svc-a")
        assert len(result["relationships"]) >= 1

    def test_dependencies(self, search, esvc, rsvc):
        a, b, _, _ = _graph(esvc, rsvc)
        result = search.natural_language_query("t", "what are dependencies of svc-a")
        assert "answer" in result

    def test_generic(self, search, esvc):
        esvc.create_entity("t", "service", "my-svc")
        result = search.natural_language_query("t", "something else")
        assert "answer" in result


class TestBFS:
    def test_basic(self, traverse, esvc, rsvc):
        a, b, c, d = _graph(esvc, rsvc)
        results = traverse.bfs(a["id"], max_depth=3)
        assert len(results) == 3

    def test_empty(self, traverse, esvc):
        e = esvc.create_entity("t", "service", "alone")
        assert traverse.bfs(e["id"]) == []


class TestDFS:
    def test_basic(self, traverse, esvc, rsvc):
        a, _, _, _ = _graph(esvc, rsvc)
        results = traverse.dfs(a["id"], max_depth=3)
        assert len(results) >= 2


class TestShortestPath:
    def test_finds(self, traverse, esvc, rsvc):
        a, _, c, _ = _graph(esvc, rsvc)
        path = traverse.shortest_path(a["id"], c["id"])
        assert path is not None
        assert len(path) == 2

    def test_none(self, traverse, esvc):
        e = esvc.create_entity("t", "service", "alone")
        f = esvc.create_entity("t", "service", "alone2")
        assert traverse.shortest_path(e["id"], f["id"]) is None


class TestAllPaths:
    def test_multiple(self, traverse, esvc, rsvc):
        a, _, c, _ = _graph(esvc, rsvc)
        paths = traverse.all_paths(a["id"], c["id"])
        assert len(paths) >= 2


class TestBlastRadius:
    def test_basic(self, traverse, esvc, rsvc):
        a, _, c, d = _graph(esvc, rsvc)
        result = traverse.blast_radius(d["id"])
        assert result["count"] >= 2

    def test_empty(self, traverse, esvc):
        e = esvc.create_entity("t", "service", "alone")
        result = traverse.blast_radius(e["id"])
        assert result["count"] == 0


class TestConnectedComponents:
    def test_two_components(self, traverse, esvc, rsvc):
        e1 = esvc.create_entity("t", "service", "a")
        e2 = esvc.create_entity("t", "service", "b")
        e3 = esvc.create_entity("t", "service", "c")
        rsvc.create_relationship("t", e1["id"], e2["id"], "DEPENDS_ON")
        comps = traverse.get_connected_components()
        assert len(comps) == 2


class TestDegreeCentrality:
    def test_basic(self, traverse, esvc, rsvc):
        a, b, c, _ = _graph(esvc, rsvc)
        centrality = traverse.get_degree_centrality()
        assert len(centrality) > 0
        assert centrality[0]["degree"] >= 1
