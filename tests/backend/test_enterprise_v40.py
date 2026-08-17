"""Enterprise Integration tests — Volume 40.

Tests for integration registry, connection lifecycle, SSO (OIDC/SAML),
SCIM provisioning, source control abstraction, session management,
service accounts, group mapping, token management, webhook validation,
rate limiting, and event normalization.
"""
import hashlib
import hmac

import pytest


# ─── Integration Registry ─────────────────────────────────────────────────

class TestIntegrationRegistry:
    def test_create_integration(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        rec = svc.create_integration(
            organization_id="org-1",
            name="GitHub",
            provider="github",
            description="GitHub integration",
        )
        assert rec.provider == "github"
        assert rec.organization_id == "org-1"
        assert rec.status == "created"
        assert rec.is_active is True

    def test_list_integrations_by_provider(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        svc.create_integration("org-1", "GitHub", "github")
        svc.create_integration("org-1", "GitLab", "gitlab")
        svc.create_integration("org-2", "GitHub 2", "github")
        github = svc.list_integrations(provider="github")
        assert len(github) == 2
        gitlab = svc.list_integrations(provider="gitlab")
        assert len(gitlab) == 1

    def test_delete_integration_removes_connections(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        rec = svc.create_integration("org-1", "GitHub", "github")
        svc.create_connection(rec.id, "org-1", "github")
        assert svc.delete_integration(rec.id) is True
        assert svc.get_integration(rec.id) is None
        assert len(svc.list_connections(integration_id=rec.id)) == 0

    def test_update_integration(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        rec = svc.create_integration("org-1", "GitHub", "github")
        updated = svc.update_integration(rec.id, name="GitHub Enterprise", status="active")
        assert updated is not None
        assert updated.name == "GitHub Enterprise"
        assert updated.status == "active"


# ─── Connection Lifecycle ─────────────────────────────────────────────────

class TestConnectionLifecycle:
    def test_full_connection_lifecycle(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        integration = svc.create_integration("org-1", "GitHub", "github")
        conn = svc.create_connection(integration.id, "org-1", "github")
        assert conn.status == "created"
        assert integration.status == "connected"

        activated = svc.activate_connection(
            conn.id,
            access_token="ghp_test123",
            scopes=["repo", "read:org"],
            provider_user_id="u123",
            provider_username="dev",
            expires_in_seconds=3600,
        )
        assert activated.status == "active"
        assert integration.status == "active"
        assert len(activated.scopes) == 2

        revoked = svc.revoke_connection(conn.id)
        assert revoked.status == "revoked"
        assert integration.status == "disconnected"
        assert revoked.access_token_ref == ""

    def test_revoke_nonexistent_returns_none(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        assert svc.revoke_connection("nonexistent") is None


# ─── Token Management ─────────────────────────────────────────────────────

class TestTokenManagement:
    def test_generate_and_hash_token(self):
        from app.enterprise.integration_service import TokenManager
        tm = TokenManager()
        token = tm.generate_token()
        assert token.startswith("nf_")
        hashed = tm.hash_token(token)
        assert len(hashed) == 64
        assert hashed == hashlib.sha256(token.encode()).hexdigest()

    def test_mask_token(self):
        from app.enterprise.integration_service import TokenManager
        tm = TokenManager()
        assert tm.mask_token("nf_abcdefghijklmnopqrstuvwxyz") == "nf_a...wxyz"
        assert tm.mask_token("short") == "***"

    def test_generate_and_validate_state(self):
        from app.enterprise.integration_service import TokenManager
        tm = TokenManager()
        state = tm.create_oauth_state("user-1", "github", "https://example.com/callback")
        assert "state" in state
        assert state["user_id"] == "user-1"
        assert tm.verify_state(state["state"], state["state"]) is True
        assert tm.verify_state("wrong", state["state"]) is False

    def test_is_token_expiring(self):
        from app.enterprise.integration_service import TokenManager
        from datetime import datetime, timezone, timedelta
        tm = TokenManager()
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        assert tm.is_token_expiring(future) is False
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert tm.is_token_expiring(past) is True


# ─── Signature Verification ───────────────────────────────────────────────

class TestSignatureVerification:
    def test_github_signature(self):
        from app.enterprise.integration_service import SignatureVerifier
        sv = SignatureVerifier()
        payload = b'{"action":"opened"}'
        secret = "my_webhook_secret"
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sv.verify_github_signature(payload, sig, secret) is True
        assert sv.verify_github_signature(payload, "sha256=wrong", secret) is False

    def test_gitlab_token(self):
        from app.enterprise.integration_service import SignatureVerifier
        sv = SignatureVerifier()
        assert sv.verify_gitlab_token("mytoken", "mytoken") is True
        assert sv.verify_gitlab_token("wrong", "mytoken") is False


# ─── Rate Limiting ────────────────────────────────────────────────────────

class TestRateLimiting:
    def test_check_rate_limit(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        result = svc.check_rate_limit("github")
        assert result["allowed"] is True
        assert result["limit"] == 60


# ─── Event Normalization ──────────────────────────────────────────────────

class TestEventNormalization:
    def test_normalize_github_pr(self):
        from app.enterprise.integration_service import EventNormalizer
        result = EventNormalizer.normalize("github", "pull_request", {"action": "opened", "number": 42})
        assert result["event_type"] == "pull_request_changed"
        assert result["source"] == "github"
        assert result["idempotency_key"]

    def test_normalize_unknown_provider(self):
        from app.enterprise.integration_service import EventNormalizer
        result = EventNormalizer.normalize("custom_tool", "something_happened", {})
        assert result["event_type"] == "custom_tool.something_happened"


# ─── Sync Jobs ────────────────────────────────────────────────────────────

class TestSyncJobs:
    def test_sync_job_lifecycle(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        integration = svc.create_integration("org-1", "GitHub", "github")
        job = svc.create_sync_job(integration.id, "org-1", "repositories", idempotency_key="key-1")
        assert job.status == "pending"
        svc.start_sync_job(job.id)
        assert job.status == "running"
        svc.complete_sync_job(job.id, records_processed=10, records_created=5)
        assert job.status == "completed"
        assert job.records_processed == 10

    def test_idempotent_sync_job(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        svc = IntegrationRegistryService()
        svc.reset()
        integration = svc.create_integration("org-1", "GitHub", "github")
        job1 = svc.create_sync_job(integration.id, "org-1", "repositories", idempotency_key="idem-1")
        job2 = svc.create_sync_job(integration.id, "org-1", "repositories", idempotency_key="idem-1")
        assert job1.id == job2.id


# ─── SSO Service ──────────────────────────────────────────────────────────

class TestSSOService:
    def test_create_oidc_connection(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        conn = svc.create_sso_connection(
            "org-1", "oidc", "Google",
            oidc_issuer="https://accounts.google.com",
            oidc_client_id="client123",
        )
        assert conn.protocol == "oidc"
        assert conn.oidc_issuer == "https://accounts.google.com"

    def test_create_saml_connection(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        conn = svc.create_sso_connection(
            "org-1", "saml", "Okta",
            saml_entity_id="https://okta.com/exk123",
            saml_sso_url="https://okta.com/app/exk123/sso/saml",
        )
        assert conn.protocol == "saml"
        assert conn.saml_entity_id == "https://okta.com/exk123"

    def test_sso_enforcement(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        svc.create_sso_connection("org-1", "oidc", "Google", is_enforced=True)
        assert svc.is_sso_enforced("org-1") is True
        assert svc.is_sso_enforced("org-2") is False

    def test_oidc_authorization_url(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        conn = svc.create_sso_connection(
            "org-1", "oidc", "Google",
            oidc_issuer="https://accounts.google.com",
            oidc_client_id="client123",
            oidc_authorization_endpoint="https://accounts.google.com/o/oauth2/auth",
        )
        url = svc.build_oidc_authorization_url(conn.id, "https://app.com/callback", "state123")
        assert "client_id=client123" in url
        assert "state=state123" in url

    def test_saml_replay_detection(self):
        from app.enterprise.sso_service import SAMLProcessor
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        assert SAMLProcessor.validate_replay(recent) is True
        old = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
        assert SAMLProcessor.validate_replay(old) is False

    def test_saml_attribute_mapping(self):
        from app.enterprise.sso_service import SAMLProcessor
        attrs = {"email": "user@example.com", "uid": "jdoe", "groups": ["admin"]}
        mapping = {"email": "email", "uid": "username"}
        result = SAMLProcessor.map_attributes(attrs, mapping)
        assert result["email"] == "user@example.com"
        assert result["username"] == "jdoe"
        assert "groups" not in result


# ─── External Identities ──────────────────────────────────────────────────

class TestExternalIdentities:
    def test_link_and_find_identity(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        identity = svc.link_identity(
            user_id="user-1", organization_id="org-1",
            provider="google", provider_user_id="google-u123",
            provider_email="user@example.com",
        )
        assert identity.provider == "google"
        found = svc.find_identity_by_provider("google", "google-u123")
        assert found is not None
        assert found.user_id == "user-1"

    def test_deactivate_identity(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        identity = svc.link_identity("user-1", "org-1", "google", "g123")
        deactivated = svc.deactivate_identity(identity.id)
        assert deactivated.is_active is False


# ─── Session Management ───────────────────────────────────────────────────

class TestSessionManagement:
    def test_create_and_revoke_session(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        session = svc.create_session("user-1", "org-1", ip_address="10.0.0.1", user_agent="Mozilla/5.0")
        assert session.revoked_at is None
        revoked = svc.revoke_session(session.id, reason="user_revoke")
        assert revoked.revoked_at is not None
        assert revoked.revoked_reason == "user_revoke"

    def test_revoke_all_sessions(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        s1 = svc.create_session("user-1", "org-1")
        s2 = svc.create_session("user-1", "org-1")
        s3 = svc.create_session("user-1", "org-1")
        count = svc.revoke_all_user_sessions("user-1", except_session_id=s1.id)
        assert count == 2
        assert svc.get_session(s1.id).revoked_at is None

    def test_detect_suspicious_sessions(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        for _ in range(5):
            svc.create_session("user-1", "org-1", user_agent="SuspiciousBot/1.0")
        suspicious = svc.detect_suspicious_sessions("user-1")
        assert len(suspicious) > 0

    def test_cleanup_expired_sessions(self):
        from app.enterprise.sso_service import SSOService
        from datetime import datetime, timezone, timedelta
        svc = SSOService()
        svc.reset()
        session = svc.create_session("user-1", "org-1")
        session.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        count = svc.cleanup_expired_sessions()
        assert count == 1
        assert svc.get_session(session.id).revoked_at is not None


# ─── Service Accounts ─────────────────────────────────────────────────────

class TestServiceAccounts:
    def test_create_service_account(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        sa = svc.create_service_account("org-1", "CI/CD Pipeline", scopes=["repo:read"])
        assert sa.name == "CI/CD Pipeline"
        assert sa.client_id.startswith("sa_")
        assert sa.is_active is True

    def test_rotate_service_account(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        sa = svc.create_service_account("org-1", "CI/CD")
        old_secret_ref = sa.client_secret_ref
        result = svc.rotate_service_account(sa.id)
        assert result is not None
        assert "client_secret" in result
        assert sa.client_secret_ref != old_secret_ref

    def test_revoke_service_account(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        sa = svc.create_service_account("org-1", "CI/CD")
        revoked = svc.revoke_service_account(sa.id)
        assert revoked.is_active is False
        assert svc.rotate_service_account(sa.id) is None


# ─── Group Mapping ────────────────────────────────────────────────────────

class TestGroupMapping:
    def test_create_group_mapping(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        mapping = svc.create_group_mapping(
            "org-1", "engineering-admins", mapped_role="admin",
            mapped_workspace_ids=["ws-1"],
        )
        assert mapping.mapped_role == "admin"
        assert "ws-1" in mapping.mapped_workspace_ids

    def test_resolve_group_roles(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        svc.create_group_mapping("org-1", "admins", mapped_role="admin")
        svc.create_group_mapping("org-1", "developers", mapped_role="member", mapped_workspace_ids=["ws-dev"])
        result = svc.resolve_group_roles("org-1", ["admins", "developers"])
        assert result["role"] == "admin"
        assert "ws-dev" in result["workspace_ids"]


# ─── SCIM Service ─────────────────────────────────────────────────────────

class TestSCIMService:
    def test_create_directory_and_provision_user(self):
        from app.enterprise.scim_service import SCIMService
        svc = SCIMService()
        svc.reset()
        d = svc.create_directory("org-1", "okta", "https://tenant.okta.com/scim/v2")
        assert d.provider == "okta"
        user = svc.provision_user(
            d.id, "org-1", "ext-001", "jdoe",
            email="jdoe@example.com", display_name="John Doe",
        )
        assert user.username == "jdoe"
        assert user.active is True

    def test_deprovision_user(self):
        from app.enterprise.scim_service import SCIMService
        svc = SCIMService()
        svc.reset()
        d = svc.create_directory("org-1", "okta", "https://okta.com/scim")
        user = svc.provision_user(d.id, "org-1", "ext-001", "jdoe")
        svc.deprovision_user(user.id)
        updated = svc.get_user(user.id)
        assert updated.active is False
        assert updated.groups == []

    def test_provision_group(self):
        from app.enterprise.scim_service import SCIMService
        svc = SCIMService()
        svc.reset()
        d = svc.create_directory("org-1", "okta", "https://okta.com/scim")
        group = svc.provision_group(d.id, "org-1", "ext-g1", "Engineering", members=["u1", "u2"])
        assert group.display_name == "Engineering"
        assert len(group.members) == 2

    def test_sync_groups_from_directory(self):
        from app.enterprise.scim_service import SCIMService
        svc = SCIMService()
        svc.reset()
        d = svc.create_directory("org-1", "okta", "https://okta.com/scim")
        groups_data = [
            {"external_id": "g1", "displayName": "Admins", "members": ["u1"]},
            {"external_id": "g2", "displayName": "Devs", "members": ["u1", "u2"]},
        ]
        result = svc.sync_groups_from_directory(d.id, groups_data)
        assert result.groups_synced == 2
        assert result.groups_created == 2

    def test_deprovision_all_for_directory(self):
        from app.enterprise.scim_service import SCIMService
        svc = SCIMService()
        svc.reset()
        d = svc.create_directory("org-1", "okta", "https://okta.com/scim")
        svc.provision_user(d.id, "org-1", "u1", "user1")
        svc.provision_user(d.id, "org-1", "u2", "user2")
        svc.provision_group(d.id, "org-1", "g1", "Group1")
        result = svc.deprovision_all_for_directory(d.id)
        assert result["users_deactivated"] == 2
        assert result["groups_deleted"] == 1


# ─── Source Control Providers ──────────────────────────────────────────────

class TestSourceControlProviders:
    def test_github_provider(self):
        from app.enterprise.providers import GitHubProvider
        gh = GitHubProvider()
        assert gh.authenticate({"access_token": "ghp_test"}) is True
        repos = gh.list_repositories("novaforge-ai")
        assert len(repos) >= 1
        assert repos[0].private is True

    def test_gitlab_provider(self):
        from app.enterprise.providers import GitLabProvider
        gl = GitLabProvider()
        assert gl.authenticate({"access_token": "glpat-test", "base_url": "https://gitlab.com"}) is True
        repos = gl.list_repositories("myorg")
        assert len(repos) >= 1

    def test_bitbucket_provider(self):
        from app.enterprise.providers import BitbucketProvider
        bb = BitbucketProvider()
        assert bb.authenticate({"access_token": "bb_test"}) is True

    def test_factory_create(self):
        from app.enterprise.providers import SourceControlFactory
        gh = SourceControlFactory.create("github", access_token="test")
        assert gh is not None
        assert gh.provider_name == "github"
        assert SourceControlFactory.create("unknown") is None
        assert "github" in SourceControlFactory.available_providers()

    def test_webhook_signature_validation(self):
        from app.enterprise.providers import GitHubProvider
        import hmac as hmac_mod
        import hashlib
        gh = GitHubProvider()
        payload = b'{"action":"opened"}'
        secret = "webhook_secret_123"
        sig = "sha256=" + hmac_mod.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert gh.validate_webhook_signature(payload, sig, secret) is True
        assert gh.validate_webhook_signature(payload, "sha256=wrong", secret) is False


# ─── Communication Providers ──────────────────────────────────────────────

class TestCommunicationProviders:
    def test_slack_provider(self):
        from app.enterprise.providers import SlackProvider
        slack = SlackProvider()
        assert slack.authenticate({"bot_token": "xoxb-test"}) is True
        channels = slack.list_channels()
        assert len(channels) >= 1

    def test_teams_provider(self):
        from app.enterprise.providers import TeamsProvider
        teams = TeamsProvider()
        assert teams.authenticate({"access_token": "test_token"}) is True

    def test_communication_factory(self):
        from app.enterprise.providers import CommunicationFactory
        assert "slack" in CommunicationFactory.available_providers()
        assert "microsoft_teams" in CommunicationFactory.available_providers()


# ─── Project Management Providers ─────────────────────────────────────────

class TestProjectManagementProviders:
    def test_jira_provider(self):
        from app.enterprise.providers import JiraProvider
        jira = JiraProvider()
        assert jira.authenticate({"base_url": "https://acme.atlassian.net", "api_token": "test"}) is True
        projects = jira.list_projects()
        assert len(projects) >= 1

    def test_pm_factory(self):
        from app.enterprise.providers import ProjectManagementFactory
        assert "jira" in ProjectManagementFactory.available_providers()


# ─── Enterprise API Smoke Tests ───────────────────────────────────────────

class TestEnterpriseAPI:
    def test_enterprise_health(self):
        from app.enterprise.integration_service import IntegrationRegistryService
        from app.enterprise.sso_service import SSOService
        from app.enterprise.scim_service import SCIMService
        IntegrationRegistryService().reset()
        SSOService().reset()
        SCIMService().reset()
        assert True

    def test_sso_metrics(self):
        from app.enterprise.sso_service import SSOService
        svc = SSOService()
        svc.reset()
        svc.create_sso_connection("org-1", "oidc", "Google")
        svc.create_session("user-1", "org-1")
        metrics = svc.get_metrics("org-1")
        assert metrics["sso_connections"] == 1
        assert metrics["active_sessions"] == 1

    def test_scim_metrics(self):
        from app.enterprise.scim_service import SCIMService
        svc = SCIMService()
        svc.reset()
        d = svc.create_directory("org-1", "okta", "https://okta.com/scim")
        svc.provision_user(d.id, "org-1", "u1", "user1")
        svc.provision_group(d.id, "org-1", "g1", "Group1")
        metrics = svc.get_metrics("org-1")
        assert metrics["directories"] == 1
        assert metrics["total_users"] == 1
        assert metrics["total_groups"] == 1
