"""Membership and Team service tests (Volume 52)."""
import pytest
from app.iam.membership_service import MembershipService
from app.iam.team_service import TeamService


@pytest.fixture()
def msvc():
    return MembershipService()


@pytest.fixture()
def tsvc():
    return TeamService()


class TestMembership:
    def test_add_member(self, msvc):
        m = msvc.add_member("org-1", "u1", "admin")
        assert m["user_id"] == "u1"
        assert m["role"] == "admin"

    def test_invite(self, msvc):
        inv = msvc.invite("org-1", "u2@test.com", "member", "admin-u1")
        assert inv["status"] == "pending"

    def test_accept_invitation(self, msvc):
        inv = msvc.invite("org-1", "u2@test.com", "member", "admin-u1")
        accepted = msvc.accept_invitation(inv["id"], "u2-id")
        assert accepted["status"] == "active"

    def test_get_membership(self, msvc):
        m = msvc.add_member("org-1", "u1", "admin")
        assert msvc.get_membership(m["id"])["user_id"] == "u1"

    def test_list_members(self, msvc):
        msvc.add_member("org-1", "u1", "admin")
        msvc.add_member("org-1", "u2", "member")
        msvc.add_member("org-2", "u3", "admin")
        assert len(msvc.list_members("org-1")) == 2

    def test_update_role(self, msvc):
        m = msvc.add_member("org-1", "u1", "member")
        updated = msvc.update_role(m["id"], "admin")
        assert updated["role"] == "admin"

    def test_remove_member(self, msvc):
        m = msvc.add_member("org-1", "u1", "member")
        assert msvc.remove_member(m["id"])
        assert msvc.get_membership(m["id"]) is None

    def test_suspend_member(self, msvc):
        m = msvc.add_member("org-1", "u1", "member")
        msvc.suspend_member(m["id"], "policy violation")
        assert msvc.get_membership(m["id"])["status"] == "suspended"

    def test_reactivate_member(self, msvc):
        m = msvc.add_member("org-1", "u1", "member")
        msvc.suspend_member(m["id"], "issue")
        msvc.reactivate_member(m["id"])
        assert msvc.get_membership(m["id"])["status"] == "active"

    def test_is_member(self, msvc):
        msvc.add_member("org-1", "u1", "member")
        assert msvc.is_member("org-1", "u1") is True
        assert msvc.is_member("org-1", "u99") is False

    def test_get_user_organizations(self, msvc):
        msvc.add_member("org-1", "u1", "member")
        msvc.add_member("org-2", "u1", "admin")
        orgs = msvc.get_user_organizations("u1")
        assert len(orgs) == 2

    def test_get_user_role(self, msvc):
        m = msvc.add_member("org-1", "u1", "admin")
        assert msvc.get_user_role("org-1", "u1") == "admin"

    def test_stats(self, msvc):
        msvc.add_member("org-1", "u1", "admin")
        msvc.add_member("org-1", "u2", "member")
        stats = msvc.get_stats("org-1")
        assert stats["total"] == 2

    def test_list_pending_invitations(self, msvc):
        msvc.invite("org-1", "a@test.com", "member", "admin-u1")
        msvc.invite("org-1", "b@test.com", "member", "admin-u1")
        pending = msvc.list_pending_invitations("org-1")
        assert len(pending) == 2


class TestTeam:
    def test_create(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        assert team["name"] == "Backend"

    def test_get(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        assert tsvc.get(team["id"])["name"] == "Backend"

    def test_list_for_org(self, tsvc):
        tsvc.create({"name": "A", "organization_id": "org-1"})
        tsvc.create({"name": "B", "organization_id": "org-1"})
        tsvc.create({"name": "C", "organization_id": "org-2"})
        assert len(tsvc.list_for_org("org-1")) == 2

    def test_update(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        updated = tsvc.update(team["id"], {"name": "Platform"})
        assert updated["name"] == "Platform"

    def test_delete(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        assert tsvc.delete(team["id"])
        assert tsvc.get(team["id"]) is None

    def test_add_member(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        tm = tsvc.add_member(team["id"], "u1")
        assert tm["user_id"] == "u1"

    def test_remove_member(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        tm = tsvc.add_member(team["id"], "u1")
        assert tsvc.remove_member(team["id"], "u1")

    def test_list_members(self, tsvc):
        team = tsvc.create({"name": "Backend", "organization_id": "org-1"})
        tsvc.add_member(team["id"], "u1")
        tsvc.add_member(team["id"], "u2")
        assert len(tsvc.list_members(team["id"])) == 2

    def test_get_user_teams(self, tsvc):
        t1 = tsvc.create({"name": "A", "organization_id": "org-1"})
        t2 = tsvc.create({"name": "B", "organization_id": "org-1"})
        tsvc.add_member(t1["id"], "u1")
        tsvc.add_member(t2["id"], "u1")
        assert len(tsvc.get_user_teams("u1")) == 2

    def test_get_child_teams(self, tsvc):
        parent = tsvc.create({"name": "Parent", "organization_id": "org-1"})
        child = tsvc.create({"name": "Child", "organization_id": "org-1", "parent_team_id": parent["id"]})
        children = tsvc.get_child_teams(parent["id"])
        assert len(children) == 1
        assert children[0]["id"] == child["id"]

    def test_stats(self, tsvc):
        tsvc.create({"name": "A", "organization_id": "org-1"})
        stats = tsvc.get_stats("org-1")
        assert stats["total"] == 1
