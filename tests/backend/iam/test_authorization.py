"""Authorization and policy tests (Volume 52)."""
import pytest
from app.iam.policy_authorizer import PolicyAuthorizer
from app.iam.resource_authorizer import ResourceAuthorizer
from app.iam.break_glass_service import BreakGlassService
from app.iam.quota_service import QuotaService
from app.iam.tenant_isolation import TenantIsolation


@pytest.fixture()
def pa():
    return PolicyAuthorizer()

@pytest.fixture()
def ra():
    return ResourceAuthorizer()

@pytest.fixture()
def bg():
    return BreakGlassService()

@pytest.fixture()
def qs():
    return QuotaService()

@pytest.fixture()
def ti():
    return TenantIsolation()


class TestPolicyAuthorizer:
    def test_create_resource_policy(self, pa):
        p = pa.create_resource_policy("org-1", "repo-read", effect="allow", actions=["repository:read"], principals=[{"type": "role", "value": "member"}])
        assert p["name"] == "repo-read"
        assert p["effect"] == "allow"

    def test_authorize_allowed(self, pa):
        result = pa.authorize("u1", "org-1", "organization:read", context={"role": "owner"})
        assert result["allowed"] is True

    def test_authorize_denied(self, pa):
        result = pa.authorize("u1", "org-1", "security:admin", context={"role": "viewer"})
        assert result["allowed"] is False

    def test_deny_overrides_allow(self, pa):
        pa.set_deny_override("org-1", "organization:read")
        result = pa.authorize("u1", "org-1", "organization:read", context={"role": "owner"})
        assert result["allowed"] is False

    def test_explain(self, pa):
        explanation = pa.explain("u1", "org-1", "organization:read", context={"role": "admin"})
        assert "rbac_has_permission" in explanation
        assert "effective_permissions" in explanation

    def test_list_resource_policies(self, pa):
        pa.create_resource_policy("org-1", "p1", actions=["org:read"])
        assert len(pa.list_resource_policies("org-1")) == 1

    def test_delete_resource_policy(self, pa):
        p = pa.create_resource_policy("org-1", "p1", actions=["org:read"])
        assert pa.delete_resource_policy(p["id"])

    def test_stats(self, pa):
        pa.authorize("u1", "org-1", "organization:read", context={"role": "admin"})
        stats = pa.get_stats()
        assert stats["total_evaluations"] >= 1


class TestResourceAuthorizer:
    def test_set_owner(self, ra):
        ra.set_resource_owner("repo-1", "repository", "u1", "org-1")
        owner = ra.get_resource_owner("repo-1")
        assert owner["owner_id"] == "u1"

    def test_grant_access(self, ra):
        grant = ra.grant_access("repo-1", "repository", "u2", ["read"], "org-1")
        assert grant["user_id"] == "u2"

    def test_revoke_access(self, ra):
        grant = ra.grant_access("repo-1", "repository", "u2", ["read"], "org-1")
        assert ra.revoke_access(grant["id"])

    def test_owner_has_access(self, ra):
        ra.set_resource_owner("repo-1", "repository", "u1", "org-1")
        result = ra.check_resource_access("u1", "repo-1", "repository", "write", "org-1")
        assert result["allowed"] is True

    def test_no_access(self, ra):
        result = ra.check_resource_access("u99", "repo-1", "repository", "repository:write", "org-1")
        assert result["allowed"] is False

    def test_list_grants_for_user(self, ra):
        ra.grant_access("repo-1", "repository", "u1", ["read"], "org-1")
        ra.grant_access("repo-2", "repository", "u1", ["read"], "org-1")
        grants = ra.list_grants_for_user("u1")
        assert len(grants) == 2


class TestBreakGlass:
    def test_request(self, bg):
        req = bg.request("org-1", "u1", "emergency", scope=["security:admin"], mfa_verified=True)
        assert "id" in req
        assert req["reason"] == "emergency"

    def test_validate(self, bg):
        req = bg.request("org-1", "u1", "emergency", mfa_verified=True)
        valid = bg.validate(req["id"])
        assert valid["valid"] is True

    def test_end(self, bg):
        req = bg.request("org-1", "u1", "emergency", mfa_verified=True)
        assert bg.end(req["id"], "resolved") is True

    def test_list_active(self, bg):
        bg.request("org-1", "u1", "emergency", mfa_verified=True)
        assert len(bg.list_active("org-1")) >= 1

    def test_cleanup(self, bg):
        count = bg.cleanup_expired()
        assert count >= 0


class TestQuota:
    def test_initialize(self, qs):
        quotas = qs.initialize_org_quotas("org-1")
        assert len(quotas) > 0

    def test_check_under_limit(self, qs):
        qs.initialize_org_quotas("org-1")
        result = qs.check_quota("org-1", "users", 1)
        assert result["allowed"] is True

    def test_consume(self, qs):
        qs.initialize_org_quotas("org-1")
        result = qs.consume_quota("org-1", "users")
        assert result["consumed"] is True

    def test_update_quota(self, qs):
        qs.initialize_org_quotas("org-1")
        updated = qs.update_quota("org-1", "users", 200)
        assert updated["limit"] == 200

    def test_usage_summary(self, qs):
        qs.initialize_org_quotas("org-1")
        summary = qs.get_usage_summary("org-1")
        assert "users" in summary


class TestTenantIsolation:
    def test_set_scope(self, ti):
        ti.set_tenant_scope("tenant-1", "organization", "org-1")
        violations = ti.get_isolation_violations("tenant-1")
        assert len(violations) == 0

    def test_validate_scope(self, ti):
        ti.set_tenant_scope("tenant-1", "organization", "org-1")
        result = ti.validate_tenant_access("tenant-1", "organization", "org-1")
        assert result["valid"] is True

    def test_validate_scope_mismatch(self, ti):
        ti.set_tenant_scope("tenant-1", "organization", "org-1")
        result = ti.validate_tenant_access("tenant-2", "organization", "org-1")
        assert result["valid"] is False

    def test_vector_filter(self, ti):
        vf = ti.create_vector_filter("tenant-1")
        assert vf["tenant_id"] == "tenant-1"

    def test_graph_filter(self, ti):
        gf = ti.create_graph_filter("tenant-1")
        assert gf["tenant_id"] == "tenant-1"

    def test_storage_path(self, ti):
        path = ti.create_storage_path("tenant-1", "data/file.txt")
        assert path == "tenants/tenant-1/data/file.txt"

    def test_violations(self, ti):
        ti.set_tenant_scope("tenant-1", "organization", "org-1")
        ti.validate_tenant_access("tenant-2", "organization", "org-1")
        violations = ti.get_isolation_violations("tenant-2")
        assert len(violations) >= 1
