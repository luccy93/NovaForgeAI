"""Unit tests for database models — validation, relationships, constraints."""

import uuid
from datetime import datetime, timezone

import pytest

from app.core.database import Base, TimestampMixin
from app.models.user import User, UserSession, ApiKey
from app.models.organization import Organization, Subscription, Project, user_organizations
from app.models.repository import Repository, Branch, Commit, RepositoryVersion
from app.models.conversation import Conversation, Message, MessageRole
from app.models.support import AuditLog, AuditAction, Notification, FeatureFlag, AgentRun, UsageRecord, SecurityReport, Deployment


class TestTimestampMixin:
    def test_has_id(self):
        assert hasattr(TimestampMixin, "id")
        assert hasattr(TimestampMixin, "created_at")
        assert hasattr(TimestampMixin, "updated_at")

    def test_id_is_uuid(self):
        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamps"
        instance = TestModel()
        assert isinstance(instance.id, uuid.UUID)

    def test_timestamps_are_datetime(self):
        import sqlalchemy
        col_type = TimestampMixin.created_at.column.type
        assert isinstance(col_type, sqlalchemy.DateTime)


class TestUserModel:
    def test_create_user(self):
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password="hashed_pw",
            full_name="Test User",
        )
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.is_active is True
        assert user.is_superuser is False
        assert isinstance(user.id, uuid.UUID)

    def test_user_defaults(self):
        user = User(email="a@b.com", username="abc", hashed_password="pw")
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.full_name is None

    def test_user_relationships(self):
        user = User(email="a@b.com", username="abc", hashed_password="pw")
        assert hasattr(user, "organizations")
        assert hasattr(user, "sessions")
        assert hasattr(user, "api_keys")
        assert hasattr(user, "notifications")


class TestOrganizationModel:
    def test_create_organization(self):
        org = Organization(name="Test Org", slug="test-org")
        assert org.name == "Test Org"
        assert org.slug == "test-org"
        assert org.is_active is True
        assert org.plan == "free"

    def test_organization_defaults(self):
        org = Organization(name="Test", slug="test")
        assert org.plan == "free"
        assert org.is_active is True


class TestRepositoryModel:
    def test_create_repository(self):
        repo = Repository(
            name="test-repo",
            full_name="org/test-repo",
            git_url="https://github.com/org/test-repo.git",
            language="python",
        )
        assert repo.name == "test-repo"
        assert repo.full_name == "org/test-repo"
        assert repo.private is True
        assert repo.default_branch == "main"
        assert repo.stars == 0

    def test_repository_relationships(self):
        repo = Repository(name="test", full_name="t/t")
        assert hasattr(repo, "branches")
        assert hasattr(repo, "commits")
        assert hasattr(repo, "versions")

    def test_repository_defaults(self):
        repo = Repository(name="test", full_name="t/t")
        assert repo.private is True
        assert repo.default_branch == "main"
        assert repo.fork is False
        assert repo.stars == 0
        assert repo.is_archived is False


class TestConversationModel:
    def test_create_conversation(self):
        conv = Conversation(session_id="sess-1", title="Test Chat")
        assert conv.session_id == "sess-1"
        assert conv.title == "Test Chat"
        assert conv.is_archived is False

    def test_conversation_relationships(self):
        conv = Conversation(session_id="sess-1")
        assert hasattr(conv, "messages")

    def test_message_creation(self):
        conv = Conversation(session_id="sess-1")
        msg = Message(
            conversation_id=conv.id,
            role=MessageRole.user,
            content="Hello!",
        )
        assert msg.role == MessageRole.user
        assert msg.content == "Hello!"

    def test_message_roles(self):
        assert MessageRole.user.value == "user"
        assert MessageRole.assistant.value == "assistant"
        assert MessageRole.system.value == "system"
        assert MessageRole.tool.value == "tool"


class TestSupportModels:
    def test_audit_log(self):
        log = AuditLog(action=AuditAction.LOGIN)
        assert log.action == AuditAction.LOGIN
        assert log.immutable is True

    def test_audit_actions(self):
        assert AuditAction.LOGIN.value == "login"
        assert AuditAction.REPOSITORY_CREATE.value == "repository_create"
        assert AuditAction.SECURITY_SCAN.value == "security_scan"

    def test_notification(self):
        notif = Notification(
            user_id=uuid.uuid4(),
            title="Test",
            body="Test body",
            notification_type="info",
        )
        assert notif.title == "Test"
        assert notif.is_read is False

    def test_feature_flag(self):
        flag = FeatureFlag(name="new-ui", enabled=True)
        assert flag.name == "new-ui"
        assert flag.enabled is True

    def test_agent_run(self):
        run = AgentRun(agent_name="planner", status="running")
        assert run.agent_name == "planner"
        assert run.status == "running"

    def test_usage_record(self):
        record = UsageRecord(
            organization_id=uuid.uuid4(),
            metric="llm_tokens",
            value=1500.0,
            recorded_at=datetime.now(timezone.utc),
        )
        assert record.metric == "llm_tokens"
        assert record.value == 1500.0

    def test_security_report(self):
        report = SecurityReport(
            repository_id=uuid.uuid4(),
            scan_type="dependency",
        )
        assert report.scan_type == "dependency"
        assert report.status == "pending"

    def test_deployment(self):
        dep = Deployment(
            environment="production",
            status="deploying",
        )
        assert dep.environment == "production"
        assert dep.status == "deploying"


class TestUserSession:
    def test_create_session(self):
        session = UserSession(
            user_id=uuid.uuid4(),
            refresh_token="rtoken123",
            expires_at=datetime.now(timezone.utc),
        )
        assert session.refresh_token == "rtoken123"
        assert session.revoked_at is None


class TestApiKey:
    def test_create_api_key(self):
        key = ApiKey(
            user_id=uuid.uuid4(),
            name="Test Key",
            key_hash="hash123",
            key_prefix="nf_",
        )
        assert key.name == "Test Key"
        assert key.key_prefix == "nf_"
        assert key.is_active is True


class TestBranch:
    def test_create_branch(self):
        branch = Branch(
            repository_id=uuid.uuid4(),
            name="feature/test",
        )
        assert branch.name == "feature/test"
        assert branch.is_default is False


class TestCommit:
    def test_create_commit(self):
        commit = Commit(
            repository_id=uuid.uuid4(),
            sha="abc123def456",
            message="Initial commit",
            author_name="Test User",
            author_email="test@example.com",
            authored_at=datetime.now(timezone.utc),
        )
        assert commit.sha == "abc123def456"
        assert commit.message == "Initial commit"


class TestRepositoryVersion:
    def test_create_version(self):
        ver = RepositoryVersion(
            repository_id=uuid.uuid4(),
            version="1.0.0",
            commit_sha="abc123",
        )
        assert ver.version == "1.0.0"
        assert ver.commit_sha == "abc123"


class TestSubscription:
    def test_create_subscription(self):
        sub = Subscription(
            organization_id=uuid.uuid4(),
            plan_id="pro",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc),
        )
        assert sub.plan_id == "pro"
        assert sub.status == "active"


class TestProject:
    def test_create_project(self):
        proj = Project(
            organization_id=uuid.uuid4(),
            name="My Project",
            slug="my-project",
        )
        assert proj.name == "My Project"
        assert proj.is_archived is False
