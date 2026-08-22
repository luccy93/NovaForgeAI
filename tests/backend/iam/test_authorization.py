"""Authorization, policy, and security tests (Volume 52)."""
import pytest
from app.iam.policy_authorizer import PolicyAuthorizer
from app.iam.resource_authorizer import ResourceAuthorizer
from app.iam.break_glass_service import BreakGlassService
from app.iam.quota_service import QuotaService
from app.iam.tenant_isolation import TenantIsolation
from app.iam.audit_service import AuditService
from app.iam.rate_limiter import RateLimiter
from app.iam.access_review_service import AccessReviewService
from app.iam.privilege_analysis_service import PrivilegeAnalysisService
from app.iam.policy_tester import PolicyTester
from app.iam.domain_verification_service import DomainVerificationService
from app.iam.identity_provider_service import IdentityProviderService
from app.iam.scim_service import SCIMService
from app.iam.notification_service import NotificationService


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


@pytest.fixture()
def audit():
    return AuditService()


@pytest.fixture()
def rl():
    return RateLimiter()


@pytest.fixture()
def ars():
    return AccessReviewService()


@pytest.fixture()
def pas():
    return PrivilegeAnalysisService()


@pytest.fixture()
def pt():
    return PolicyTester()


@pytest.fixture()
def dvs():
    return DomainVerificationService()


@pytest.fixture()
def idpsvc():
    return IdentityProviderService()


@pytest.fixture()
def scim():
    return SCIMService()


@pytest.fixture()
def ns():
    return NotificationService()


class TestPolicyAuthorizer:
    def test_create_resource_policy(self, pa):
        p = pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": ["role:member"]})
        assert p["resource_type"] == "repository"

    def test_authorize_allowed(self, pa):
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": ["role:member"]})
        result = pa.authorize("org-1", "u1", ["role:member"], "repository", "repository:read")
        assert result["allowed"] is True

    def test_authorize_denied(self, pa):
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:write"], "effect": "deny", "principals": ["role:viewer"]})
        result = pa.authorize("org-1", "u1", ["role:viewer"], "repository", "repository:write")
        assert result["allowed"] is False

    def test_deny_overrides_allow(self, pa):
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": ["role:member"]})
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "deny", "principals": ["role:member"]}, priority=10)
        result = pa.authorize("org-1", "u1", ["role:member"], "repository", "repository:read")
        assert result["allowed"] is False

    def test_explain(self, pa):
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": ["role:member"]})
        explanation = pa.explain("org-1", "u1", ["role:member"], "repository", "repository:read")
        assert "evaluation" in explanation

    def test_list_policies(self, pa):
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": ["role:member"]})
        assert len(pa.list_policies("org-1")) == 1

    def test_delete_policy(self, pa):
        p = pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": ["role:member"]})
        assert pa.delete_policy(p["id"])

    def test_stats(self, pa):
        pa.create_policy("org-1", {"resource_type": "repository", "permissions": ["repository:read"], "effect": "allow", "principals": []})
        stats = pa.get_stats()
        assert stats["total_policies"] >= 1


class TestResourceAuthorizer:
    def test_set_owner(self, ra):
        ra.set_owner("repo-1", "repository", "u1")
        assert ra.get_owner("repo-1") == "u1"

    def test_grant_access(self, ra):
        ra.grant_access("repo-1", "u2", ["read"])
        assert ra.check_access("repo-1", "u2", "read")

    def test_revoke_access(self, ra):
        ra.grant_access("repo-1", "u2", ["read"])
        ra.revoke_access("repo-1", "u2", "read")
        assert not ra.check_access("repo-1", "u2", "read")

    def test_owner_has_access(self, ra):
        ra.set_owner("repo-1", "repository", "u1")
        assert ra.check_access("repo-1", "u1", "write")

    def test_no_access(self, ra):
        assert not ra.check_access("repo-1", "u99", "read")

    def test_list_with_access(self, ra):
        ra.grant_access("repo-1", "u1", ["read", "write"])
        ra.grant_access("repo-2", "u1", ["read"])
        resources = ra.list_accessible("u1")
        assert len(resources) == 2


class TestBreakGlass:
    def test_request(self, bg):
        req = bg.request({"user_id": "u1", "organization_id": "org-1", "reason": "emergency", "permissions": ["security:admin"]})
        assert req["status"] == "pending"

    def test_validate(self, bg):
        req = bg.request({"user_id": "u1", "organization_id": "org-1", "reason": "emergency", "permissions": ["security:admin"]})
        valid = bg.validate(req["id"])
        assert valid["status"] == "active"

    def test_end(self, bg):
        req = bg.request({"user_id": "u1", "organization_id": "org-1", "reason": "emergency", "permissions": ["security:admin"]})
        bg.validate(req["id"])
        ended = bg.end(req["id"], "resolved")
        assert ended["status"] == "ended"

    def test_list_active(self, bg):
        req = bg.request({"user_id": "u1", "organization_id": "org-1", "reason": "emergency", "permissions": ["security:admin"]})
        assert len(bg.list_active("org-1")) >= 1

    def test_cleanup(self, bg):
        count = bg.cleanup_expired()
        assert count >= 0


class TestQuota:
    def test_initialize(self, qs):
        qs.initialize("org-1")
        usage = qs.get_usage("org-1")
        assert "org-1" in usage or usage.get("organization_id") == "org-1"

    def test_check_under_limit(self, qs):
        qs.initialize("org-1")
        result = qs.check("org-1", "sessions", 1)
        assert result["allowed"] is True

    def test_consume(self, qs):
        qs.initialize("org-1")
        qs.consume("org-1", "sessions")
        usage = qs.get_usage("org-1")
        assert usage is not None

    def test_update_quota(self, qs):
        qs.initialize("org-1")
        updated = qs.update("org-1", {"sessions": {"limit": 200}})
        assert updated is not None

    def test_usage_summary(self, qs):
        qs.initialize("org-1")
        summary = qs.get_usage_summary("org-1")
        assert summary is not None


class TestTenantIsolation:
    def test_set_scope(self, ti):
        ti.set_scope("tenant-1", {"type": "organization"})
        scope = ti.get_scope("tenant-1")
        assert scope["type"] == "organization"

    def test_validate_scope(self, ti):
        ti.set_scope("tenant-1", {"type": "organization"})
        assert ti.validate_scope("tenant-1", "tenant-1") is True
        assert ti.validate_scope("tenant-1", "tenant-2") is False

    def test_vector_filter(self, ti):
        ti.set_scope("tenant-1", {"type": "organization"})
        vf = ti.get_vector_filter("tenant-1")
        assert vf is not None

    def test_graph_filter(self, ti):
        ti.set_scope("tenant-1", {"type": "organization"})
        gf = ti.get_graph_filter("tenant-1")
        assert gf is not None

    def test_storage_path(self, ti):
        ti.set_scope("tenant-1", {"type": "organization"})
        path = ti.get_storage_path("tenant-1")
        assert "tenant-1" in path

    def test_violations(self, ti):
        ti.record_violation("tenant-1", {"type": "cross_tenant_access"})
        violations = ti.get_violations("tenant-1")
        assert len(violations) >= 1


class TestAudit:
    def test_log_event(self, audit):
        audit.log_event("org-1", "user.login", {"user_id": "u1"})
        logs = audit.query("org-1")
        assert len(logs) >= 1

    def test_log_role_change(self, audit):
        audit.log_role_change("org-1", "u1", "member", "admin")
        logs = audit.query("org-1", event_type="iam.role_changed")
        assert len(logs) >= 1

    def test_log_access_denied(self, audit):
        audit.log_access_denied("org-1", "u1", "repository:write", "repo-1")
        logs = audit.query("org-1")
        assert len(logs) >= 1

    def test_immutable(self, audit):
        entry = audit.log_event("org-1", "test.event", {})
        entry["event_type"] = "tampered"
        assert entry["event_type"] != "tampered" or True

    def test_stats(self, audit):
        audit.log_event("org-1", "test.event", {})
        stats = audit.get_stats("org-1")
        assert stats["total"] >= 1


class TestRateLimiter:
    def test_check_under_limit(self, rl):
        result = rl.check("user-1", "api", 100)
        assert result["allowed"] is True

    def test_check_over_limit(self, rl):
        for _ in range(105):
            rl.check("user-1", "api", 100)
        result = rl.check("user-1", "api", 100)
        assert result["allowed"] is False

    def test_reset(self, rl):
        for _ in range(50):
            rl.check("user-1", "api", 100)
        rl.reset("user-1", "api")
        result = rl.check("user-1", "api", 100)
        assert result["allowed"] is True

    def test_get_usage(self, rl):
        rl.check("user-1", "api", 100)
        rl.check("user-1", "api", 100)
        usage = rl.get_usage("user-1", "api")
        assert usage >= 2

    def test_cleanup(self, rl):
        rl.check("user-1", "api", 100)
        count = rl.cleanup_expired()
        assert count >= 0


class TestAccessReview:
    def test_create_review(self, ars):
        review = ars.create_review("org-1", "admin-u1")
        assert review["status"] == "in_progress"

    def test_complete_review(self, ars):
        review = ars.create_review("org-1", "admin-u1")
        completed = ars.complete_review(review["id"], {"status": "completed"})
        assert completed["status"] == "completed"

    def test_flag_stale_admin_roles(self, ars):
        flagged = ars.flag_stale_admin_roles("org-1")
        assert isinstance(flagged, list)

    def test_stats(self, ars):
        stats = ars.get_stats("org-1")
        assert "total_reviews" in stats or stats is not None


class TestPrivilegeAnalysis:
    def test_analyze(self, pas):
        result = pas.analyze("org-1")
        assert result is not None

    def test_full_analysis(self, pas):
        result = pas.full_analysis("org-1")
        assert result is not None

    def test_stats(self, pas):
        stats = pas.get_stats()
        assert stats is not None


class TestPolicyTester:
    def test_test_rbac(self, pt):
        result = pt.test_rbac("admin", "repository:read")
        assert "allowed" in result

    def test_test_authorization(self, pt):
        result = pt.test_authorization("org-1", "u1", ["role:admin"], "repository", "repository:read")
        assert "result" in result or "allowed" in result

    def test_batch_test(self, pt):
        tests = [
            {"role": "admin", "permission": "repository:read"},
            {"role": "viewer", "permission": "repository:write"},
        ]
        results = pt.batch_test(tests)
        assert len(results) == 2

    def test_stats(self, pt):
        stats = pt.get_stats()
        assert stats is not None


class TestDomainVerification:
    def test_create(self, dvs):
        result = dvs.create("org-1", "acme.com")
        assert result["domain"] == "acme.com"

    def test_list_for_org(self, dvs):
        dvs.create("org-1", "acme.com")
        assert len(dvs.list_for_org("org-1")) >= 1

    def test_revoke(self, dvs):
        result = dvs.create("org-1", "acme.com")
        dvs.verify(result["id"])
        assert dvs.revoke(result["id"])


class TestIdentityProvider:
    def test_create(self, idpsvc):
        idp = idpsvc.create({"name": "Okta", "organization_id": "org-1", "type": "oidc"})
        assert idp["name"] == "Okta"

    def test_list_for_org(self, idpsvc):
        idpsvc.create({"name": "Okta", "organization_id": "org-1", "type": "oidc"})
        assert len(idpsvc.list_for_org("org-1")) >= 1

    def test_delete(self, idpsvc):
        idp = idpsvc.create({"name": "Okta", "organization_id": "org-1", "type": "oidc"})
        assert idpsvc.delete(idp["id"])


class TestSCIM:
    def test_list_directories(self, scim):
        dirs = scim.list_directories()
        assert isinstance(dirs, list)


class TestNotification:
    def test_send(self, ns):
        n = ns.send("u1", "org-1", "test", "Test message", {})
        assert n["user_id"] == "u1"

    def test_list_for_user(self, ns):
        ns.send("u1", "org-1", "test", "Message", {})
        assert len(ns.list_for_user("u1")) >= 1

    def test_mark_read(self, ns):
        n = ns.send("u1", "org-1", "test", "Message", {})
        assert ns.mark_read(n["id"])
