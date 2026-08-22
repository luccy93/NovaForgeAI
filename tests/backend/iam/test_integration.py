"""Audit, rate limiter, access review, and integration service tests (Volume 52)."""
import pytest
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
def audit():
    return AuditService()

@pytest.fixture()
def rl():
    return RateLimiter()

@pytest.fixture()
def ars():
    return AccessReviewService()

@pytest.fixture()
def pas_svc():
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


class TestAudit:
    def test_log_event(self, audit):
        entry = audit.log("org-1", "u1", "user", "user.login")
        assert entry["action"] == "user.login"
        assert entry["immutable"] is True

    def test_log_role_change(self, audit):
        entry = audit.log_role_change("org-1", "admin-u1", "u1", "member", "admin")
        assert entry["action"] == "role_change"

    def test_log_access_denied(self, audit):
        entry = audit.log_access_denied("org-1", "u1", "repository:write", "repository", "repo-1")
        assert entry["action"] == "access_denied"

    def test_immutable(self, audit):
        entry = audit.log("org-1", "u1", "user", "test.event")
        assert entry["immutable"] is True

    def test_stats(self, audit):
        audit.log("org-1", "u1", "user", "test.event")
        stats = audit.get_stats("org-1")
        assert stats["total_entries"] >= 1

    def test_query(self, audit):
        audit.log("org-1", "u1", "user", "login")
        audit.log("org-1", "u1", "user", "logout")
        logs = audit.query("org-1", action="login")
        assert len(logs) == 1


class TestRateLimiter:
    def test_check_under_limit(self, rl):
        result = rl.check("user-1", limit=100)
        assert result["allowed"] is True

    def test_check_over_limit(self, rl):
        for _ in range(100):
            rl.check("user-1", limit=5)
        result = rl.check("user-1", limit=5)
        assert result["allowed"] is False

    def test_reset(self, rl):
        for _ in range(3):
            rl.check("user-1", limit=5)
        rl.reset("user-1")
        result = rl.check("user-1", limit=5)
        assert result["allowed"] is True

    def test_get_usage(self, rl):
        rl.check("user-1", limit=100)
        rl.check("user-1", limit=100)
        usage = rl.get_usage("user-1")
        assert usage["count"] >= 2

    def test_cleanup(self, rl):
        rl.check("user-1", limit=100)
        count = rl.cleanup()
        assert count >= 0


class TestAccessReview:
    def test_create_review(self, ars):
        review = ars.create_review("org-1", "periodic", initiated_by="admin-u1")
        assert review["status"] == "pending"

    def test_complete_review(self, ars):
        review = ars.create_review("org-1", "periodic")
        completed = ars.complete_review(review["id"], {"findings": 0})
        assert completed["status"] == "completed"

    def test_flag_stale_admin_roles(self, ars):
        memberships = [{"user_id": "u1", "role": "admin", "is_active": True, "joined_at": "2020-01-01T00:00:00Z"}]
        flagged = ars.flag_stale_admin_roles("org-1", memberships)
        assert len(flagged) == 1

    def test_stats(self, ars):
        ars.create_review("org-1", "periodic")
        stats = ars.get_stats("org-1")
        assert stats["total_reviews"] >= 1


class TestPrivilegeAnalysis:
    def test_analyze_unused_admin_roles(self, pas_svc):
        memberships = [{"user_id": "u1", "role": "admin", "is_active": True}]
        result = pas_svc.analyze_unused_admin_roles("org-1", memberships)
        assert result["analysis_type"] == "unused_admin_roles"
        assert len(result["findings"]) >= 1

    def test_full_analysis(self, pas_svc):
        memberships = [{"user_id": "u1", "role": "admin", "is_active": True}]
        result = pas_svc.run_full_analysis("org-1", memberships, [], [], [])
        assert result["total_analyses"] >= 1

    def test_stats(self, pas_svc):
        memberships = [{"user_id": "u1", "role": "admin", "is_active": True}]
        pas_svc.analyze_unused_admin_roles("org-1", memberships)
        analyses = pas_svc.get_analyses("org-1")
        assert len(analyses) >= 1


class TestPolicyTester:
    def test_test_rbac(self, pt):
        result = pt.test_rbac("admin", "organization:read")
        assert result["test_type"] == "rbac"
        assert "result" in result

    def test_test_full_authorization(self, pt):
        result = pt.test_full_authorization("u1", "org-1", "organization:read", context={"role": "admin"})
        assert result["test_type"] == "full_authorization"

    def test_batch_test(self, pt):
        tests = [
            {"test_type": "rbac", "role": "admin", "permission": "organization:read"},
            {"test_type": "rbac", "role": "viewer", "permission": "organization:write"},
        ]
        results = pt.batch_test(tests)
        assert results["total"] == 2

    def test_stats(self, pt):
        pt.test_rbac("admin", "organization:read")
        stats = pt.get_stats()
        assert stats["total_tests"] >= 1


class TestDomainVerification:
    def test_create(self, dvs):
        result = dvs.create_verification("org-1", "acme.com")
        assert result["domain"] == "acme.com"

    def test_list_for_org(self, dvs):
        dvs.create_verification("org-1", "acme.com")
        assert len(dvs.list_for_org("org-1")) >= 1

    def test_verify_and_revoke(self, dvs):
        result = dvs.create_verification("org-1", "acme.com")
        dvs.verify(result["id"], proof=result["verification_token"])
        assert dvs.revoke(result["id"])


class TestIdentityProvider:
    def test_create(self, idpsvc):
        idp = idpsvc.create("org-1", "Okta", "oidc", issuer="https://okta.com", client_id="cid123")
        assert idp["name"] == "Okta"

    def test_list_for_org(self, idpsvc):
        idpsvc.create("org-1", "Okta", "oidc")
        assert len(idpsvc.list_for_org("org-1")) >= 1

    def test_delete(self, idpsvc):
        idp = idpsvc.create("org-1", "Okta", "oidc")
        assert idpsvc.delete(idp["id"])


class TestSCIM:
    def test_create_directory_and_list(self, scim):
        scim.create_directory("org-1", "LDAP", "ldap")
        assert len(scim.list_directories("org-1")) == 1


class TestNotification:
    def test_send(self, ns):
        n = ns.send("org-1", "u1", "test", "Test", "Test message")
        assert n["user_id"] == "u1"

    def test_list_for_user(self, ns):
        ns.send("org-1", "u1", "test", "Title", "Message")
        assert len(ns.list_for_user("u1")) >= 1

    def test_mark_read(self, ns):
        n = ns.send("org-1", "u1", "test", "Title", "Message")
        assert ns.mark_read(n["id"])
