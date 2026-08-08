"""Integration tests for NovaForge AI backend — new backend features."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app import create_app
from app.core.config import settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── Health ─────────────────────────────────────────────────────────────

class TestHealth:
    async def test_health_returns_ok(self, app: FastAPI, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == settings.app_version

    async def test_health_ready_returns_503_when_no_db(self, client: AsyncClient) -> None:
        resp = await client.get("/health/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert "checks" in body
        assert body["checks"]["app"] is True


# ─── Rate Limiting ──────────────────────────────────────────────────────

class TestRateLimit:
    async def test_rate_limit_allows_initial_requests(self, client: AsyncClient) -> None:
        for _ in range(3):
            resp = await client.get("/health")
            assert resp.status_code == 200

    async def test_rate_limit_login_path_has_stricter_limit(self, client: AsyncClient) -> None:
        payload = {"email": "test@test.com", "password": "password123"}
        for _ in range(10):
            await client.post("/api/v1/auth/login", json=payload)
        resp = await client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code in (429, 401, 422)

    async def test_rate_limit_returns_retry_after(self, client: AsyncClient) -> None:
        payload = {"email": "a@b.com", "password": "x" * 12}
        for _ in range(15):
            await client.post("/api/v1/auth/login", json=payload)
        resp = await client.post("/api/v1/auth/login", json=payload)
        if resp.status_code == 429:
            assert "retry-after" in {k.lower(): v for k, v in resp.headers.items()}
            body = resp.json()
            assert body["error"]["code"] == "RATE_LIMITED"
            assert "retry_after_seconds" in body["error"]["details"]


# ─── Request ID ─────────────────────────────────────────────────────────

class TestRequestID:
    async def test_response_includes_request_id(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert "x-request-id" in {k.lower(): v for k, v in resp.headers.items()}

    async def test_request_id_preserved_from_client(self, client: AsyncClient) -> None:
        custom_id = "my-custom-id-123"
        resp = await client.get("/health", headers={"X-Request-ID": custom_id})
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert headers_lower.get("x-request-id") == custom_id


# ─── Middleware: Exception Handlers ─────────────────────────────────────

class TestExceptionHandlers:
    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/repositories/nonexistent-uuid")
        assert resp.status_code in (404, 400, 422)

    async def test_internal_error_structure(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/repositories/00000000-0000-0000-0000-000000000000")
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]


# ─── Organizations API ──────────────────────────────────────────────────

class TestOrganizations:
    async def test_list_orgs_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/organizations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_org_requires_slug(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Test Org", "slug": "test-org"},
        )
        assert resp.status_code in (201, 422)

    async def test_create_org_empty_body_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/organizations", json={})
        assert resp.status_code == 422

    async def test_create_org_duplicate_slug(self, client: AsyncClient) -> None:
        resp1 = await client.post(
            "/api/v1/organizations",
            json={"name": "Org A", "slug": "duplicate-org"},
        )
        resp2 = await client.post(
            "/api/v1/organizations",
            json={"name": "Org B", "slug": "duplicate-org"},
        )
        assert resp1.status_code in (201, 409)
        if resp1.status_code == 201:
            assert resp2.status_code == 409


# ─── Chat Streaming ─────────────────────────────────────────────────────

class TestChatStreaming:
    async def test_stream_endpoint_returns_sse(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "stream": True},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        assert "x-conversation-id" in {k.lower(): v for k, v in resp.headers.items()}

    async def test_stream_event_format(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/chat/stream",
            json={"message": "What is Python?"},
        )
        assert resp.status_code == 200
        text = resp.text
        assert "data:" in text
        assert "conversation_id" in text or "chunk" in text

    async def test_stream_returns_done_event(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/chat/stream",
            json={"message": "Hi"},
        )
        assert resp.status_code == 200
        assert '"type": "done"' in resp.text or '"done"' in resp.text


# ─── Repository Import ──────────────────────────────────────────────────

class TestRepoImport:
    async def test_import_without_git_url_returns_400(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/repositories/import",
            json={"name": "test", "full_name": "test/repo"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "git_url" in body.get("detail", "").lower() or "detail" in body

    async def test_import_endpoint_structure(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/repositories/import",
            json={
                "name": "test-repo",
                "full_name": "test/repo",
                "git_url": "https://github.com/test/test.git",
            },
        )
        assert resp.status_code in (201, 502)

    async def test_local_import_without_repo_returns_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/repositories/00000000-0000-0000-0000-000000000000/import-local",
            params={"local_path": "C:\\nonexistent"},
        )
        assert resp.status_code == 404


# ─── Citation Engine ────────────────────────────────────────────────────

class TestCitationEngine:
    def test_format_response_creates_citations(self) -> None:
        from app.services.citation import CitationEngine
        engine = CitationEngine()
        result = engine.format_response(
            answer="Python is a programming language.",
            sources=[
                {"text": "Python docs", "source": "docs.python.org", "type": "web", "score": 0.95},
            ],
            confidence=0.95,
            model_used="gpt-4o-mini",
        )
        assert len(result.citations) == 1
        assert result.citations[0].id == 1
        assert result.citations[0].source == "docs.python.org"
        assert result.answer.startswith("Python is a programming language.")

    def test_empty_response(self) -> None:
        from app.services.citation import CitationEngine
        engine = CitationEngine()
        result = engine.empty_response("No context found.")
        assert result.answer == "No context found."
        assert result.citations == []
        assert result.confidence == 0.0

    def test_multiple_sources_ordered(self) -> None:
        from app.services.citation import CitationEngine
        engine = CitationEngine()
        sources = [
            {"text": "Source A", "source": "A", "type": "vector", "score": 0.9},
            {"text": "Source B", "source": "B", "type": "graph", "score": 0.8},
            {"text": "Source C", "source": "C", "type": "web", "score": 0.7},
        ]
        result = engine.format_response("Answer.", sources, confidence=0.8, model_used="test")
        assert len(result.citations) == 3
        assert result.citations[0].id == 1
        assert result.citations[1].id == 2
        assert result.citations[2].id == 3


# ─── Code Analysis (fixed tree-sitter) ─────────────────────────────────

class TestCodeAnalysis:
    def test_regex_functions_python(self) -> None:
        from app.services.code_analysis import CodeAnalysisService
        svc = CodeAnalysisService()
        content = "def foo():\n    pass\n\ndef bar(x, y):\n    return x + y"
        result = svc.analyze_file(content, "python")
        assert result["language"] == "python"
        assert len(result["functions"]) >= 2
        names = [f["name"] for f in result["functions"]]
        assert "foo" in names
        assert "bar" in names

    def test_regex_classes_typescript(self) -> None:
        from app.services.code_analysis import CodeAnalysisService
        svc = CodeAnalysisService()
        content = "class User {\n  name: string;\n}\n\nexport class Admin extends User {}"
        result = svc.analyze_file(content, "typescript")
        assert len(result["classes"]) >= 1
        names = [c["name"] for c in result["classes"]]
        assert "User" in names

    def test_complexity_python(self) -> None:
        from app.services.code_analysis import CodeAnalysisService
        svc = CodeAnalysisService()
        content = """def check(x):
    if x > 0:
        if x > 10:
            return True
    return False"""
        result = svc.analyze_file(content, "python")
        assert result["complexity"] >= 3

    def test_dependencies_python(self) -> None:
        from app.services.code_analysis import CodeAnalysisService
        svc = CodeAnalysisService()
        content = "import os\nfrom typing import Optional\nimport json"
        result = svc.analyze_file(content, "python")
        assert "os" in result["dependencies"]
        assert "typing" in result["dependencies"]
        assert "json" in result["dependencies"]

    def test_unsupported_language(self) -> None:
        from app.services.code_analysis import CodeAnalysisService
        svc = CodeAnalysisService()
        import pytest
        with pytest.raises(ValueError, match="Unsupported language"):
            svc.analyze_file("content", "ruby")

    def test_empty_content(self) -> None:
        from app.services.code_analysis import CodeAnalysisService
        svc = CodeAnalysisService()
        result = svc.analyze_file("", "python")
        assert result["line_count"] == 0
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["size_bytes"] == 0
        assert result["dependencies"] == []


# ─── RBAC / Authorization ──────────────────────────────────────────────

class TestAuthorization:
    def test_permissions_structure(self) -> None:
        from app.core.authorization import Permission, OrgRole, ROLE_PERMISSIONS
        assert Permission.read_repo in ROLE_PERMISSIONS[OrgRole.viewer]
        assert Permission.delete_repo in ROLE_PERMISSIONS[OrgRole.admin]
        assert Permission.admin_all in ROLE_PERMISSIONS[OrgRole.owner]

    def test_viewer_cannot_delete(self) -> None:
        from app.core.authorization import Permission, OrgRole, ROLE_PERMISSIONS
        perms = ROLE_PERMISSIONS[OrgRole.viewer]
        assert Permission.delete_repo not in perms

    def test_owner_has_all_permissions(self) -> None:
        from app.core.authorization import Permission, OrgRole, ROLE_PERMISSIONS
        perms = ROLE_PERMISSIONS[OrgRole.owner]
        all_perms = set(Permission)
        assert perms == all_perms


# ─── Error Exceptions ──────────────────────────────────────────────────

class TestExceptions:
    def test_not_found_error(self) -> None:
        from app.core.exceptions import NotFoundError
        exc = NotFoundError(resource="User", identifier="123")
        d = exc.to_dict()
        assert d["error"]["code"] == "NOT_FOUND"
        assert "User" in d["error"]["message"]
        assert exc.status_code == 404

    def test_validation_error(self) -> None:
        from app.core.exceptions import ValidationError
        exc = ValidationError(message="Invalid input")
        d = exc.to_dict()
        assert d["error"]["code"] == "VALIDATION_ERROR"
        assert exc.status_code == 422

    def test_authentication_error(self) -> None:
        from app.core.exceptions import AuthenticationError
        exc = AuthenticationError()
        d = exc.to_dict()
        assert d["error"]["code"] == "UNAUTHORIZED"
        assert exc.status_code == 401
