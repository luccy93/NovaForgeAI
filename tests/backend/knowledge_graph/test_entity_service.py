"""EntityService tests (Volume 51)."""
import pytest
from app.knowledge_graph.entity_service import EntityService


@pytest.fixture()
def svc():
    return EntityService()


class TestEntityCRUD:
    def test_create_entity(self, svc):
        e = svc.create_entity("t", "repository", "repo-a")
        assert e["id"]
        assert e["tenant"] == "t"
        assert e["entity_type"] == "repository"
        assert e["name"] == "repo-a"
        assert e["status"] == "active"
        assert e["version"] == 1

    def test_create_entity_defaults(self, svc):
        e = svc.create_entity("t", "service", "svc")
        assert e["display_name"] == "svc"
        assert e["external_id"] == ""
        assert e["aliases"] == []

    def test_get_entity(self, svc):
        e = svc.create_entity("t", "service", "svc")
        got = svc.get_entity(e["id"])
        assert got["name"] == "svc"

    def test_get_entity_not_found(self, svc):
        assert svc.get_entity("nonexistent") is None

    def test_update_entity(self, svc):
        e = svc.create_entity("t", "service", "old")
        updated = svc.update_entity(e["id"], name="new", description="desc")
        assert updated["name"] == "new"
        assert updated["description"] == "desc"
        assert updated["version"] == 2

    def test_update_entity_not_found(self, svc):
        assert svc.update_entity("x", name="y") is None

    def test_delete_entity(self, svc):
        e = svc.create_entity("t", "service", "svc")
        assert svc.delete_entity(e["id"]) is True
        assert svc.get_entity(e["id"])["status"] == "deleted"

    def test_delete_entity_not_found(self, svc):
        assert svc.delete_entity("x") is False


class TestEntityQuery:
    def test_list_empty(self, svc):
        assert svc.list_entities("t") == []

    def test_list_by_type(self, svc):
        svc.create_entity("t", "service", "a")
        svc.create_entity("t", "repository", "b")
        assert len(svc.list_entities("t", entity_type="service")) == 1

    def test_list_by_tenant(self, svc):
        svc.create_entity("t1", "service", "a")
        svc.create_entity("t2", "service", "b")
        assert len(svc.list_entities("t1")) == 1

    def test_list_by_provider(self, svc):
        svc.create_entity("t", "service", "a", provider="aws")
        svc.create_entity("t", "service", "b", provider="gcp")
        assert len(svc.list_entities("t", provider="aws")) == 1

    def test_list_by_name_contains(self, svc):
        svc.create_entity("t", "service", "payment-api")
        svc.create_entity("t", "service", "auth-api")
        assert len(svc.list_entities("t", name_contains="payment")) == 1

    def test_list_pagination(self, svc):
        for i in range(5):
            svc.create_entity("t", "service", f"svc-{i}")
        page = svc.list_entities("t", limit=2, offset=0)
        assert len(page) == 2

    def test_search_entities_exact(self, svc):
        svc.create_entity("t", "service", "payment-svc")
        results = svc.search_entities("t", "payment-svc")
        assert len(results) >= 1
        assert results[0]["name"] == "payment-svc"

    def test_search_entities_partial(self, svc):
        svc.create_entity("t", "service", "payment-svc")
        svc.create_entity("t", "service", "auth-svc")
        results = svc.search_entities("t", "payment")
        assert len(results) == 1

    def test_search_entities_by_description(self, svc):
        svc.create_entity("t", "service", "my-svc", description="handles payments")
        results = svc.search_entities("t", "payments")
        assert len(results) == 1

    def test_search_entities_by_alias(self, svc):
        e = svc.create_entity("t", "service", "my-svc")
        svc.add_alias(e["id"], "github", "org/my-svc")
        results = svc.search_entities("t", "org/my-svc")
        assert len(results) == 1


class TestEntityExternalId:
    def test_get_by_external_id(self, svc):
        svc.create_entity("t", "service", "svc", external_id="ext-1", provider="github")
        found = svc.get_entity_by_external_id("ext-1", "github", "t")
        assert found is not None
        assert found["name"] == "svc"

    def test_get_by_external_id_not_found(self, svc):
        assert svc.get_entity_by_external_id("x", "y", "t") is None


class TestEntityAliases:
    def test_add_alias(self, svc):
        e = svc.create_entity("t", "service", "svc")
        alias = svc.add_alias(e["id"], "github", "org/svc")
        assert alias["value"] == "org/svc"

    def test_remove_alias(self, svc):
        e = svc.create_entity("t", "service", "svc")
        svc.add_alias(e["id"], "github", "org/svc")
        assert svc.remove_alias(e["id"], "github", "org/svc") is True

    def test_list_aliases(self, svc):
        e = svc.create_entity("t", "service", "svc")
        svc.add_alias(e["id"], "github", "org/svc")
        aliases = svc.list_aliases(e["id"])
        assert len(aliases) == 1

    def test_get_entity_by_alias(self, svc):
        e = svc.create_entity("t", "service", "svc")
        svc.add_alias(e["id"], "github", "org/svc")
        found = svc.get_entity_by_alias("org/svc", "t")
        assert found["id"] == e["id"]


class TestEntityBulkStats:
    def test_bulk_create(self, svc):
        result = svc.bulk_create_entities("t", [
            {"name": "a", "entity_type": "service"},
            {"name": "b", "entity_type": "service"},
            {"name": "", "entity_type": "service"},
        ])
        assert result["created"] == 2
        assert result["skipped"] == 1

    def test_get_entity_stats(self, svc):
        svc.create_entity("t", "service", "a")
        svc.create_entity("t", "repository", "b")
        stats = svc.get_entity_stats("t")
        assert stats["total"] == 2
        assert stats["by_type"]["service"] == 1

    def test_merge_entities(self, svc):
        e1 = svc.create_entity("t", "service", "a")
        e2 = svc.create_entity("t", "service", "b")
        svc.add_alias(e2["id"], "github", "org/b")
        result = svc.merge_entities(e1["id"], e2["id"])
        assert result["merged_into"] == e2["id"]
        assert result["aliases_moved"] == 1
        assert svc.get_entity(e1["id"])["status"] == "deleted"

    def test_merge_not_found(self, svc):
        result = svc.merge_entities("x", "y")
        assert "error" in result

    def test_version_increments(self, svc):
        e = svc.create_entity("t", "service", "svc")
        for i in range(3):
            svc.update_entity(e["id"], name=f"svc-{i}")
        assert svc.get_entity(e["id"])["version"] == 4
