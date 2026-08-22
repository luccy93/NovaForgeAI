"""Organization, Workspace, Project service tests (Volume 52)."""
import pytest
from app.iam.organization_service import OrganizationService
from app.iam.workspace_service import WorkspaceService
from app.iam.project_service import ProjectService


@pytest.fixture()
def osvc():
    return OrganizationService()


@pytest.fixture()
def wsvc():
    return WorkspaceService()


@pytest.fixture()
def psvc():
    return ProjectService()


class TestOrganization:
    def test_create(self, osvc):
        org = osvc.create({"name": "Acme Corp", "slug": "acme", "owner_id": "u1"})
        assert org["name"] == "Acme Corp"
        assert org["slug"] == "acme"

    def test_get(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        fetched = osvc.get(org["id"])
        assert fetched["name"] == "Acme"

    def test_get_by_slug(self, osvc):
        osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        fetched = osvc.get_by_slug("acme")
        assert fetched is not None

    def test_update(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        updated = osvc.update(org["id"], {"name": "Acme Corp"})
        assert updated["name"] == "Acme Corp"

    def test_delete(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        assert osvc.delete(org["id"])
        assert osvc.get(org["id"]) is None

    def test_suspend(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        osvc.suspend(org["id"], "billing issue")
        assert osvc.get(org["id"])["status"] == "suspended"

    def test_reactivate(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        osvc.suspend(org["id"], "issue")
        osvc.reactivate(org["id"])
        assert osvc.get(org["id"])["status"] == "active"

    def test_list_all(self, osvc):
        osvc.create({"name": "A", "slug": "a", "owner_id": "u1"})
        osvc.create({"name": "B", "slug": "b", "owner_id": "u1"})
        assert len(osvc.list_all()) == 2

    def test_list_active(self, osvc):
        o1 = osvc.create({"name": "A", "slug": "a", "owner_id": "u1"})
        osvc.create({"name": "B", "slug": "b", "owner_id": "u1"})
        osvc.suspend(o1["id"], "issue")
        assert len(osvc.list_active()) == 1

    def test_stats(self, osvc):
        osvc.create({"name": "A", "slug": "a", "owner_id": "u1"})
        stats = osvc.get_stats()
        assert stats["total"] == 1

    def test_check_state(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        assert osvc.check_state(org["id"])["active"] is True

    def test_check_state_suspended(self, osvc):
        org = osvc.create({"name": "Acme", "slug": "acme", "owner_id": "u1"})
        osvc.suspend(org["id"], "issue")
        assert osvc.check_state(org["id"])["active"] is False

    def test_get_not_found(self, osvc):
        assert osvc.get("nonexistent") is None


class TestWorkspace:
    def test_create(self, wsvc):
        ws = wsvc.create({"name": "Engineering", "slug": "engineering", "organization_id": "org-1"})
        assert ws["name"] == "Engineering"

    def test_get(self, wsvc):
        ws = wsvc.create({"name": "Eng", "slug": "eng", "organization_id": "org-1"})
        assert wsvc.get(ws["id"])["name"] == "Eng"

    def test_list_for_org(self, wsvc):
        wsvc.create({"name": "A", "slug": "a", "organization_id": "org-1"})
        wsvc.create({"name": "B", "slug": "b", "organization_id": "org-1"})
        wsvc.create({"name": "C", "slug": "c", "organization_id": "org-2"})
        assert len(wsvc.list_for_org("org-1")) == 2

    def test_update(self, wsvc):
        ws = wsvc.create({"name": "Eng", "slug": "eng", "organization_id": "org-1"})
        updated = wsvc.update(ws["id"], {"name": "Platform"})
        assert updated["name"] == "Platform"

    def test_delete(self, wsvc):
        ws = wsvc.create({"name": "Eng", "slug": "eng", "organization_id": "org-1"})
        assert wsvc.delete(ws["id"])
        assert wsvc.get(ws["id"]) is None

    def test_get_by_slug(self, wsvc):
        wsvc.create({"name": "Eng", "slug": "eng", "organization_id": "org-1"})
        found = wsvc.get_by_slug("org-1", "eng")
        assert found is not None

    def test_stats(self, wsvc):
        wsvc.create({"name": "A", "slug": "a", "organization_id": "org-1"})
        stats = wsvc.get_stats("org-1")
        assert stats["total"] == 1


class TestProject:
    def test_create(self, psvc):
        proj = psvc.create({"name": "API", "slug": "api", "workspace_id": "ws-1", "organization_id": "org-1"})
        assert proj["name"] == "API"

    def test_get(self, psvc):
        proj = psvc.create({"name": "API", "slug": "api", "workspace_id": "ws-1", "organization_id": "org-1"})
        assert psvc.get(proj["id"])["name"] == "API"

    def test_list_for_workspace(self, psvc):
        psvc.create({"name": "A", "slug": "a", "workspace_id": "ws-1", "organization_id": "org-1"})
        psvc.create({"name": "B", "slug": "b", "workspace_id": "ws-1", "organization_id": "org-1"})
        psvc.create({"name": "C", "slug": "c", "workspace_id": "ws-2", "organization_id": "org-1"})
        assert len(psvc.list_for_workspace("ws-1")) == 2

    def test_list_for_org(self, psvc):
        psvc.create({"name": "A", "slug": "a", "workspace_id": "ws-1", "organization_id": "org-1"})
        psvc.create({"name": "B", "slug": "b", "workspace_id": "ws-2", "organization_id": "org-2"})
        assert len(psvc.list_for_org("org-1")) == 1

    def test_update(self, psvc):
        proj = psvc.create({"name": "API", "slug": "api", "workspace_id": "ws-1", "organization_id": "org-1"})
        updated = psvc.update(proj["id"], {"name": "Backend"})
        assert updated["name"] == "Backend"

    def test_delete(self, psvc):
        proj = psvc.create({"name": "API", "slug": "api", "workspace_id": "ws-1", "organization_id": "org-1"})
        assert psvc.delete(proj["id"])
        assert psvc.get(proj["id"]) is None

    def test_archive(self, psvc):
        proj = psvc.create({"name": "API", "slug": "api", "workspace_id": "ws-1", "organization_id": "org-1"})
        psvc.archive(proj["id"])
        assert psvc.get(proj["id"])["status"] == "archived"

    def test_stats(self, psvc):
        psvc.create({"name": "A", "slug": "a", "workspace_id": "ws-1", "organization_id": "org-1"})
        stats = psvc.get_stats("org-1")
        assert stats["total"] == 1
