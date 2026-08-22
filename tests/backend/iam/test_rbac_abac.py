"""RBAC and ABAC engine tests (Volume 52)."""
import pytest
from app.iam.constants import IAMRole, IAMPermission, ROLE_PERMISSIONS
from app.iam.rbac_engine import RBACEngine
from app.iam.abac_engine import ABACEngine


@pytest.fixture()
def rbac():
    return RBACEngine()


@pytest.fixture()
def abac():
    return ABACEngine()


class TestRBAC:
    def test_owner_has_all_permissions(self, rbac):
        perms = rbac.resolve_role_permissions("owner")
        assert IAMPermission.ORG_READ in perms
        assert IAMPermission.SECURITY_ADMIN in perms
        assert IAMPermission.BILLING_ADMIN in perms

    def test_viewer_lacks_write_permission(self, rbac):
        assert not rbac.check_permission("viewer", IAMPermission.ORG_WRITE)

    def test_check_permission_allowed(self, rbac):
        assert rbac.check_permission("admin", IAMPermission.MEMBER_MANAGE)

    def test_check_permission_denied(self, rbac):
        assert not rbac.check_permission("member", IAMPermission.SECURITY_ADMIN)

    def test_evaluate_access_allowed(self, rbac):
        result = rbac.evaluate_access("admin", "organization:read")
        assert result["allowed"] is True

    def test_evaluate_access_denied(self, rbac):
        result = rbac.evaluate_access("viewer", "organization:write")
        assert result["allowed"] is False

    def test_create_custom_role(self, rbac):
        role = rbac.create_custom_role("org-1", "deployer", ["agent:execute", "environment:deploy"])
        assert role["name"] == "deployer"
        assert len(role["permissions"]) == 2

    def test_custom_role_permissions(self, rbac):
        rbac.create_custom_role("org-1", "deployer", ["agent:execute"])
        assert rbac.check_permission("deployer", IAMPermission.AGENT_EXECUTE)

    def test_update_custom_role(self, rbac):
        role = rbac.create_custom_role("org-1", "deployer", ["agent:execute"])
        updated = rbac.update_custom_role(role["id"], {"permissions": ["agent:execute", "environment:deploy"]})
        assert len(updated["permissions"]) == 2

    def test_delete_custom_role(self, rbac):
        role = rbac.create_custom_role("org-1", "temp", [])
        assert rbac.delete_custom_role(role["id"])
        assert rbac.get_role(role["id"]) is None

    def test_get_role(self, rbac):
        role = rbac.create_custom_role("org-1", "tester", ["project:read"])
        assert rbac.get_role(role["id"])["name"] == "tester"

    def test_list_roles(self, rbac):
        rbac.create_custom_role("org-1", "r1", [])
        rbac.create_custom_role("org-2", "r2", [])
        assert len(rbac.list_roles("org-1")) == 1

    def test_role_hierarchy(self, rbac):
        children = rbac.get_role_hierarchy("owner")
        assert "admin" in children
        assert "sre" in children

    def test_admin_role_permissions(self, rbac):
        perms = rbac.resolve_role_permissions("admin")
        assert IAMPermission.REPOSITORY_WRITE in perms
        assert IAMPermission.MEMBER_MANAGE in perms

    def test_sre_role_permissions(self, rbac):
        perms = rbac.resolve_role_permissions("sre")
        assert IAMPermission.ENVIRONMENT_DEPLOY in perms
        assert IAMPermission.AGENT_EXECUTE in perms

    def test_security_role_permissions(self, rbac):
        perms = rbac.resolve_role_permissions("security")
        assert IAMPermission.SECURITY_ADMIN in perms
        assert IAMPermission.AUDIT_READ in perms

    def test_resolve_role_permissions_with_inheritance(self, rbac):
        rbac.create_custom_role("org-1", "custom", ["data:export"])
        perms = rbac.resolve_role_permissions("viewer", ["custom"])
        assert IAMPermission.ORG_READ in perms
        assert IAMPermission.DATA_EXPORT in perms

    def test_evaluation_log(self, rbac):
        rbac.evaluate_access("owner", "organization:read")
        rbac.evaluate_access("viewer", "organization:write")
        log = rbac.get_evaluation_log()
        assert len(log) == 2

    def test_stats(self, rbac):
        rbac.create_custom_role("org-1", "r1", ["project:read"])
        stats = rbac.get_stats()
        assert stats["custom_roles"] == 1


class TestABAC:
    def test_create_condition_equals(self, abac):
        policy = abac.create_policy("env_check", "repository", "repository:write", "allow", conditions=[{"field": "environment", "operator": "equals", "value": "development"}])
        assert len(policy["conditions"]) == 1

    def test_create_condition_in(self, abac):
        abac.create_policy("region_check", "repository", "repository:read", "allow", conditions=[{"field": "region", "operator": "in", "value": ["us-east", "eu-west"]}])
        result = abac.evaluate("repository", "repository:read", {"region": "us-east"})
        assert result["decision"] == "allowed"

    def test_create_condition_not_in(self, abac):
        abac.create_policy("block_restricted", "document", "document:read", "deny", denied_conditions=[{"field": "classification", "operator": "in", "value": ["SECRET"]}])

    def test_evaluate_allow(self, abac):
        abac.create_policy("test", "service", "service:deploy", "allow", conditions=[{"field": "environment", "operator": "equals", "value": "staging"}])
        result = abac.evaluate("service", "service:deploy", {"environment": "staging"})
        assert result["decision"] == "allowed"

    def test_evaluate_deny(self, abac):
        abac.create_policy("test", "service", "service:deploy", "allow", conditions=[{"field": "environment", "operator": "equals", "value": "production"}], denied_conditions=[{"field": "environment", "operator": "equals", "value": "production", "description": "production blocked"}])
        result = abac.evaluate("service", "service:deploy", {"environment": "production"})
        assert result["decision"] == "denied"

    def test_priority_order(self, abac):
        abac.create_policy("low", "repo", "repo:write", "allow", priority=1)
        abac.create_policy("high", "repo", "repo:write", "allow", priority=10, denied_conditions=[{"field": "block", "operator": "equals", "value": True, "description": "blocked"}])
        result = abac.evaluate("repo", "repo:write", {"block": True})
        assert result["decision"] == "denied"

    def test_no_matching_policies(self, abac):
        result = abac.evaluate("repo", "repo:write", {})
        assert result["decision"] == "not_applicable"

    def test_delete_policy(self, abac):
        p = abac.create_policy("test", "repo", "repo:read", "allow")
        assert abac.delete_policy(p["id"])

    def test_list_policies(self, abac):
        abac.create_policy("p1", "repo", "repo:read", "allow")
        abac.create_policy("p2", "service", "service:deploy", "allow")
        assert len(abac.list_policies("repo")) == 1

    def test_simulate(self, abac):
        abac.create_policy("test", "repo", "repo:read", "allow", conditions=[{"field": "tenant", "operator": "equals", "value": "org-1"}])
        result = abac.simulate("repo", "repo:read", {"tenant": "org-1"})
        assert result["simulation"] is True

    def test_stats(self, abac):
        abac.create_policy("p1", "repo", "repo:read", "allow")
        stats = abac.get_stats()
        assert stats["total_policies"] == 1
