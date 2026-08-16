"""Unit tests for core modules — Config, Logging, Audit, Tenancy."""

import os
import uuid
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Request, Response


class TestSettings:
    def test_default_values(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from app.core.config import Settings
        s = Settings(_env_file=None)
        assert s.app_name == "NovaForge AI"
        assert s.app_version == "0.1.0"
        assert s.debug is False
        assert s.database_url == "postgresql+asyncpg://postgres:postgres@localhost:5432/novaforge"
        assert s.neo4j_uri == "bolt://localhost:7687"
        assert s.neo4j_user == "neo4j"
        assert s.neo4j_password == "password"
        assert s.qdrant_url == "http://localhost:6333"
        assert s.redis_url == "redis://localhost:6379/0"
        assert s.openai_api_key is None
        assert s.anthropic_api_key is None
        assert s.google_api_key is None
        assert s.jwt_secret == "change-me-in-production"
        assert s.jwt_algorithm == "HS256"
        assert s.access_token_expire_minutes == 30
        assert s.cors_origins == ["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"]
        assert s.github_app_id is None
        assert s.github_app_private_key is None
        assert s.github_webhook_secret is None
        assert s.sentry_dsn is None
        assert s.github_app_id is None
        assert s.log_level == "INFO"
        assert s.sentry_dsn is None
        assert s.rate_limit_auth_max == 100
        assert s.rate_limit_default_max == 200
        assert s.rate_limit_window_seconds == 60

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("APP_NAME", "NovaForge Test")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb")
        monkeypatch.setenv("JWT_SECRET", "super-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("RATE_LIMIT_AUTH_MAX", "50")
        from app.core.config import Settings
        s = Settings(_env_file=None)
        assert s.app_name == "NovaForge Test"
        assert s.debug is True
        assert s.database_url == "postgresql+asyncpg://test:test@localhost:5432/testdb"
        assert s.jwt_secret == "super-secret"
        assert s.openai_api_key == "sk-test123"
        assert s.rate_limit_auth_max == 50

    def test_extra_ignored(self, monkeypatch):
        monkeypatch.setenv("UNKNOWN_VAR", "should be ignored")
        from app.core.config import Settings
        s = Settings()
        assert not hasattr(s, "unknown_var")

    def test_settings_instantiated(self):
        from app.core.config import settings
        assert isinstance(settings.app_name, str)

    def test_cors_origins_list(self):
        from app.core.config import Settings
        s = Settings(_env_file=None)
        assert isinstance(s.cors_origins, list)
        assert "http://localhost:3000" in s.cors_origins

    def test_optional_api_keys(self):
        from app.core.config import Settings
        s = Settings(_env_file=None)
        assert s.openai_api_key is None
        assert s.anthropic_api_key is None
        assert s.google_api_key is None
        assert s.github_app_id is None
        assert s.github_app_private_key is None
        assert s.github_webhook_secret is None
        assert s.sentry_dsn is None

    def test_rate_limit_defaults(self):
        from app.core.config import Settings
        s = Settings(_env_file=None)
        assert s.rate_limit_auth_max == 100
        assert s.rate_limit_default_max == 200
        assert s.rate_limit_window_seconds == 60


class TestLogging:
    def test_configure_logging_sets_level(self):
        from app.core.logging import configure_logging
        root = logging.getLogger()
        old_level = root.level
        configure_logging("DEBUG")
        assert root.level == logging.DEBUG
        root.setLevel(old_level)

    def test_configure_logging_default_info(self):
        from app.core.logging import configure_logging
        root = logging.getLogger()
        old_level = root.level
        configure_logging()
        assert root.level == logging.INFO
        root.setLevel(old_level)

    def test_configure_logging_invalid_level_defaults_info(self):
        from app.core.logging import configure_logging
        root = logging.getLogger()
        old_level = root.level
        configure_logging("INVALID")
        assert root.level == logging.INFO
        root.setLevel(old_level)

    def test_configure_logging_does_not_add_duplicate_handlers(self):
        from app.core.logging import configure_logging
        root = logging.getLogger()
        old_count = len(root.handlers)
        configure_logging("INFO")
        configure_logging("INFO")
        configure_logging("DEBUG")
        assert len(root.handlers) == old_count or len(root.handlers) == 1

    def test_request_id_filter_init(self):
        from app.core.logging import RequestIDFilter
        f = RequestIDFilter()
        assert f._request_id == ""

    def test_request_id_filter_set(self):
        from app.core.logging import RequestIDFilter
        f = RequestIDFilter()
        f.set_request_id("req-123")
        assert f._request_id == "req-123"

    def test_request_id_filter_adds_attributes(self):
        from app.core.logging import RequestIDFilter
        f = RequestIDFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = f.filter(record)
        assert result is True
        assert hasattr(record, "request_id")
        assert hasattr(record, "timestamp")

    def test_request_id_filter_default_dash(self):
        from app.core.logging import RequestIDFilter
        f = RequestIDFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.request_id == "-"

    def test_request_id_filter_preserves_existing(self):
        from app.core.logging import RequestIDFilter
        f = RequestIDFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.request_id = "existing-id"
        f.filter(record)
        assert record.request_id == "existing-id"

    def test_get_request_id_filter_returns_singleton(self):
        from app.core.logging import get_request_id_filter, RequestIDFilter
        f1 = get_request_id_filter()
        f2 = get_request_id_filter()
        assert f1 is f2
        assert isinstance(f1, RequestIDFilter)

    def test_get_logger_has_filter(self):
        from app.core.logging import get_logger
        logger = get_logger("test.module")
        assert any(isinstance(f, logging.Filter) for f in logger.filters)
        assert logger.name == "test.module"


class TestAuditMiddleware:
    def test_register_audit_middleware(self):
        from app.core.audit import register_audit_middleware, AuditMiddleware
        app = Mock()
        app.add_middleware = Mock()
        register_audit_middleware(app)
        app.add_middleware.assert_called_once_with(AuditMiddleware)

    def test_path_action_map_contains_expected(self):
        from app.core.audit import PATH_ACTION_MAP
        assert "/api/v1/auth/login" in PATH_ACTION_MAP
        assert "/api/v1/auth/register" in PATH_ACTION_MAP
        assert "/api/v1/repositories" in PATH_ACTION_MAP
        assert "/api/v1/repositories/import" in PATH_ACTION_MAP

    @pytest.mark.asyncio
    async def test_dispatch_passthrough_for_non_mutating(self):
        from app.core.audit import AuditMiddleware
        app = AsyncMock()
        middleware = AuditMiddleware(app)
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/v1/health"
        response = Response(status_code=200)
        call_next = AsyncMock(return_value=response)
        result = await middleware.dispatch(request, call_next)
        assert result.status_code == 200

    def test_resolve_action_exact_match(self):
        from app.core.audit import AuditMiddleware, AuditAction
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        result = middleware._resolve_action(request)
        assert result == AuditAction.LOGIN

    def test_resolve_action_delete_repo(self):
        from app.core.audit import AuditMiddleware, AuditAction
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/repositories/123"
        request.method = "DELETE"
        with patch.object(middleware, '_resolve_action', wraps=middleware._resolve_action) as wrapped:
            result = middleware._resolve_action(request)
        assert result == AuditAction.REPOSITORY_DELETE

    def test_resolve_action_delete_org(self):
        from app.core.audit import AuditMiddleware, AuditAction
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/organizations/456"
        request.method = "DELETE"
        result = middleware._resolve_action(request)
        assert result == AuditAction.ORGANIZATION_DELETE

    def test_resolve_action_permission_change(self):
        from app.core.audit import AuditMiddleware, AuditAction
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/organizations/456/permissions"
        result = middleware._resolve_action(request)
        assert result == AuditAction.PERMISSION_CHANGE

    def test_resolve_action_unknown(self):
        from app.core.audit import AuditMiddleware
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/unknown"
        result = middleware._resolve_action(request)
        assert result is None

    def test_resolve_resource_type(self):
        from app.core.audit import AuditMiddleware
        middleware = AuditMiddleware(Mock())
        cases = [
            ("/api/v1/repositories/123", "repositories"),
            ("/api/v1/organizations/456", "organizations"),
            ("/api/v1/users/789", "users"),
            ("/api/v1/projects/abc", "projects"),
            ("/api/v1/health", None),
        ]
        for path, expected in cases:
            request = Mock(spec=Request)
            request.url.path = path
            result = middleware._resolve_resource_type(request)
            assert result == expected

    def test_extract_resource_id(self):
        from app.core.audit import AuditMiddleware
        middleware = AuditMiddleware(Mock())
        cases = [
            ("/api/v1/repositories/abc-123", "abc-123"),
            ("/api/v1/organizations/456", "456"),
            ("/api/v1/users/789", "789"),
            ("/api/v1/projects/proj-1", "proj-1"),
            ("/api/v1/repositories", None),
            ("/api/v1/health", None),
        ]
        for path, expected in cases:
            request = Mock(spec=Request)
            request.url.path = path
            result = middleware._extract_resource_id(request)
            assert result == expected

    @pytest.mark.asyncio
    async def test_log_audit_skips_when_no_action(self):
        from app.core.audit import AuditMiddleware
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/health"
        response = Response(status_code=200)
        with patch.object(middleware, '_resolve_action', return_value=None):
            result = await middleware._log_audit(request, response)
        assert result is None

    @pytest.mark.asyncio
    async def test_log_audit_exception_caught(self):
        from app.core.audit import AuditMiddleware, AuditAction
        middleware = AuditMiddleware(Mock())
        request = Mock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.method = "POST"
        request.client.host = "127.0.0.1"
        request.headers = {"user-agent": "test"}
        response = Response(status_code=200)
        with patch.object(middleware, '_resolve_action', return_value=AuditAction.LOGIN):
            await middleware._log_audit(request, response)


class TestTenancy:
    def test_tenant_context_set_and_get(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        org_id = uuid.uuid4()
        TenantContext.set(org_id)
        assert TenantContext.get() == org_id
        TenantContext.clear()

    def test_tenant_context_get_none_when_empty(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        assert TenantContext.get() is None

    def test_tenant_context_set_overwrites(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        TenantContext.set(uuid.uuid4())
        new_id = uuid.uuid4()
        TenantContext.set(new_id)
        assert TenantContext.get() == new_id
        TenantContext.clear()

    def test_tenant_context_clear(self):
        from app.core.tenancy import TenantContext
        TenantContext.set(uuid.uuid4())
        TenantContext.clear()
        assert TenantContext.get() is None

    def test_tenant_context_is_class_level(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        t1 = TenantContext()
        t2 = TenantContext()
        org_id = uuid.uuid4()
        t1.set(org_id)
        assert t2.get() == org_id
        TenantContext.clear()

    def test_get_filter_returns_none_without_org(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        assert TenantContext.get_filter() is None

    def test_get_filter_returns_tuple_with_org(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        org_id = uuid.uuid4()
        TenantContext.set(org_id)
        result = TenantContext.get_filter()
        assert result is not None
        clause, params = result
        assert "organization_id = :tenant_org_id" in str(clause)
        assert params["tenant_org_id"] == str(org_id)
        TenantContext.clear()

    def test_get_filter_custom_column(self):
        from app.core.tenancy import TenantContext
        TenantContext.clear()
        org_id = uuid.uuid4()
        TenantContext.set(org_id)
        result = TenantContext.get_filter("custom_org_id")
        assert result is not None
        clause, params = result
        assert "custom_org_id = :tenant_org_id" in str(clause)
        TenantContext.clear()

    def test_register_tenant_middleware(self):
        from app.core.tenancy import register_tenant_middleware, TenantMiddleware
        app = Mock()
        app.add_middleware = Mock()
        register_tenant_middleware(app)
        app.add_middleware.assert_called_once_with(TenantMiddleware)

    def test_extract_org_id_from_header(self):
        from app.core.tenancy import TenantMiddleware
        middleware = TenantMiddleware(Mock())
        org_id = uuid.uuid4()
        request = Mock(spec=Request)
        request.headers = {"X-Organization-ID": str(org_id)}
        request.url.path = "/api/v1/repositories"
        result = middleware._extract_org_id(request)
        assert result == org_id

    def test_extract_org_id_from_path(self):
        from app.core.tenancy import TenantMiddleware
        middleware = TenantMiddleware(Mock())
        org_id = uuid.uuid4()
        request = Mock(spec=Request)
        request.headers = {}
        request.url.path = f"/api/v1/organizations/{org_id}/repositories"
        result = middleware._extract_org_id(request)
        assert result == org_id

    def test_extract_org_id_invalid_uuid(self):
        from app.core.tenancy import TenantMiddleware
        middleware = TenantMiddleware(Mock())
        request = Mock(spec=Request)
        request.headers = {"X-Organization-ID": "not-a-uuid"}
        request.url.path = "/api/v1/repositories"
        result = middleware._extract_org_id(request)
        assert result is None

    def test_extract_org_id_missing(self):
        from app.core.tenancy import TenantMiddleware
        middleware = TenantMiddleware(Mock())
        request = Mock(spec=Request)
        request.headers = {}
        request.url.path = "/api/v1/health"
        result = middleware._extract_org_id(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_sets_and_clears_context(self):
        from app.core.tenancy import TenantMiddleware, TenantContext
        middleware = TenantMiddleware(Mock())
        org_id = uuid.uuid4()
        request = Mock(spec=Request)
        request.headers = {"X-Organization-ID": str(org_id)}
        request.url.path = "/api/v1/repositories"
        request.state = Mock()
        response = Response(status_code=200)
        call_next = AsyncMock(return_value=response)
        result = await middleware.dispatch(request, call_next)
        assert result.status_code == 200
        assert TenantContext.get() is None
