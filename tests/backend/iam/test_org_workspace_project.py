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
        org = osvc.create("Acme Corp", "acme", "u1")
        assert org["name"] == "Acme Corp"
        assert org["slug"] == "acme"

    def test_get(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        fetched = osvc.get(org["id"])
        assert fetched["name"] == "Acme"

    def test_get_by_slug(self, osvc):
        osvc.create("Acme", "acme", "u1")
        fetched = osvc.get_by_slug("acme")
        assert fetched is not None

    def test_update(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        updated = osvc.update(org["id"], {"name": "Acme Corp"})
        assert updated["name"] == "Acme Corp"

    def test_delete(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        assert osvc.delete(org["id"])
        assert osvc.get(org["id"])["is_active"] is False

    def test_suspend(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        osvc.suspend(org["id"], "billing issue")
        assert osvc.get(org["id"])["state"] == "SUSPENDED"

    def test_reactivate(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        osvc.suspend(org["id"], "issue")
        osvc.reactivate(org["id"])
        assert osvc.get(org["id"])["state"] == "ACTIVE"

    def test_list_all(self, osvc):
        osvc.create("A", "a", "u1")
        osvc.create("B", "b", "u1")
        assert len(osvc.list_all()) == 2

    def test_list_active(self, osvc):
        o1 = osvc.create("A", "a", "u1")
        osvc.create("B", "b", "u1")
        osvc.suspend(o1["id"], "issue")
        assert len(osvc.list_active()) == 1

    def test_stats(self, osvc):
        org = osvc.create("A", "a", "u1")
        stats = osvc.get_stats(org["id"])
        assert stats["name"] == "A"
        assert stats["state"] == "ACTIVE"

    def test_check_state(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        assert osvc.check_state(org["id"]) == "ACTIVE"

    def test_check_state_suspended(self, osvc):
        org = osvc.create("Acme", "acme", "u1")
        osvc.suspend(org["id"], "issue")
        assert osvc.check_state(org["id"]) == "SUSPENDED"

    def test_get_not_found(self, osvc):
        assert osvc.get("nonexistent") is None


class TestWorkspace:
    def test_create(self, wsvc):
        ws = wsvc.create("org-1", "Engineering", "engineering")
        assert ws["name"] == "Engineering"

    def test_get(self, wsvc):
        ws = wsvc.create("org-1", "Eng", "eng")
        assert wsvc.get(ws["id"])["name"] == "Eng"

    def test_list_for_org(self, wsvc):
        wsvc.create("org-1", "A", "a")
        wsvc.create("org-1", "B", "b")
        wsvc.create("org-2", "C", "c")
        assert len(wsvc.list_for_org("org-1")) == 2

    def test_update(self, wsvc):
        ws = wsvc.create("org-1", "Eng", "eng")
        updated = wsvc.update(ws["id"], {"name": "Platform"})
        assert updated["name"] == "Platform"

    def test_delete(self, wsvc):
        ws = wsvc.create("org-1", "Eng", "eng")
        assert wsvc.delete(ws["id"])
        assert wsvc.get(ws["id"]) is None

    def test_get_by_slug(self, wsvc):
        wsvc.create("org-1", "Eng", "eng")
        found = wsvc.get_by_slug("org-1", "eng")
        assert found is not None

    def test_stats(self, wsvc):
        wsvc.create("org-1", "A", "a")
        stats = wsvc.get_stats("org-1")
        assert stats["total"] == 1


class TestProject:
    def test_create(self, psvc):
        proj = psvc.create("org-1", "ws-1", "API", "api")
        assert proj["name"] == "API"

    def test_get(self, psvc):
        proj = psvc.create("org-1", "ws-1", "API", "api")
        assert psvc.get(proj["id"])["name"] == "API"

    def test_list_for_workspace(self, psvc):
        psvc.create("org-1", "ws-1", "A", "a")
        psvc.create("org-1", "ws-1", "B", "b")
        psvc.create("org-1", "ws-2", "C", "c")
        assert len(psvc.list_for_workspace("ws-1")) == 2

    def test_list_for_org(self, psvc):
        psvc.create("org-1", "ws-1", "A", "a")
        psvc.create("org-2", "ws-2", "B", "b")
        assert len(psvc.list_for_org("org-1")) == 1

    def test_update(self, psvc):
        proj = psvc.create("org-1", "ws-1", "API", "api")
        updated = psvc.update(proj["id"], {"name": "Backend"})
        assert updated["name"] == "Backend"

    def test_delete(self, psvc):
        proj = psvc.create("org-1", "ws-1", "API", "api")
        assert psvc.delete(proj["id"])
        assert psvc.get(proj["id"]) is None

    def test_archive(self, psvc):
        proj = psvc.create("org-1", "ws-1", "API", "api")
        assert psvc.archive(proj["id"])
        assert psvc.get(proj["id"])["is_archived"] is True

    def test_stats(self, psvc):
        psvc.create("org-1", "ws-1", "A", "a")
        stats = psvc.get_stats("org-1")
        assert stats["total"] == 1
