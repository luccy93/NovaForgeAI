"""API endpoint comprehensive tests — auth, chat, repositories, organizations, agents, code analysis.

Focuses on response schemas, validation, error handling, and pagination.
"""

import uuid
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


class TestHealthEndpoints:
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    async def test_health_ready(self, client: AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "checks" in body
        assert "app" in body["checks"]

    async def test_health_method_not_allowed(self, client: AsyncClient):
        resp = await client.post("/health")
        assert resp.status_code == 405

    async def test_health_ready_slow(self, client: AsyncClient):
        resp = await client.get("/health/ready", timeout=30)
        assert resp.status_code in (200, 503)


class TestRootEndpoint:
    async def test_root_not_found(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 404

    async def test_docs_redirect(self, client: AsyncClient):
        resp = await client.get("/docs", follow_redirects=False)
        assert resp.status_code in (200, 307, 404)


class TestCORS:
    async def test_cors_headers_present(self, client: AsyncClient):
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in {k.lower(): v for k, v in resp.headers.items()}

    async def test_cors_blocked_origin(self, client: AsyncClient):
        resp = await client.options(
            "/health",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        headers = {k.lower(): v for k, v in resp.headers.items()}
        assert headers.get("access-control-allow-origin") != "https://evil.com"

    async def test_cors_allows_credentials(self, client: AsyncClient):
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "GET",
            },
        )
        headers = {k.lower(): v for k, v in resp.headers.items()}
        assert headers.get("access-control-allow-credentials") == "true"


class TestAgentEndpoints:
    async def test_list_agents(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert isinstance(agents, list)

    async def test_run_agent_requires_input(self, client: AsyncClient):
        resp = await client.post("/api/v1/agents/planner/run", json={})
        assert resp.status_code == 422

    async def test_run_agent_invalid_name(self, client: AsyncClient):
        resp = await client.post("/api/v1/agents/nonexistent/run", json={"input": "test"})
        assert resp.status_code in (404, 422)

    async def test_run_pipeline_requires_agents(self, client: AsyncClient):
        resp = await client.post("/api/v1/agents/pipeline", json={"input": "test", "agents": []})
        assert resp.status_code == 422

    async def test_run_pipeline_invalid_agent(self, client: AsyncClient):
        resp = await client.post("/api/v1/agents/pipeline", json={
            "input": "test",
            "agents": ["invalid_agent_name"],
        })
        assert resp.status_code in (200, 404, 422)

    async def test_run_parallel(self, client: AsyncClient):
        resp = await client.post("/api/v1/agents/parallel", json={
            "input": "test",
            "agents": ["planner"],
        })
        assert resp.status_code in (200, 404, 422)


class TestCodeAnalysisEndpoints:
    async def test_analyze_python(self, client: AsyncClient, sample_python_code):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": sample_python_code,
            "language": "python",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "python"
        assert len(body["functions"]) >= 3
        assert len(body["classes"]) >= 1
        assert body["complexity"] >= 1

    async def test_analyze_typescript(self, client: AsyncClient, sample_typescript_code):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": sample_typescript_code,
            "language": "typescript",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "typescript"
        assert len(body["functions"]) >= 2
        assert len(body["classes"]) >= 1

    async def test_analyze_go(self, client: AsyncClient, sample_go_code):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": sample_go_code,
            "language": "go",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "go"

    async def test_analyze_rust(self, client: AsyncClient, sample_rust_code):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": sample_rust_code,
            "language": "rust",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "rust"

    async def test_analyze_java(self, client: AsyncClient, sample_java_code):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": sample_java_code,
            "language": "java",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "java"

    async def test_analyze_unsupported_language(self, client: AsyncClient):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": "code",
            "language": "ruby",
        })
        assert resp.status_code == 422

    async def test_analyze_empty_content(self, client: AsyncClient):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": "",
            "language": "python",
        })
        assert resp.status_code == 422


class TestRepositoryEndpoints:
    async def test_list_repos_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/repositories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_repo(self, client: AsyncClient):
        resp = await client.post("/api/v1/repositories", json={
            "name": "test-repo",
            "full_name": "test/test-repo",
            "language": "python",
        })
        assert resp.status_code == 201

    async def test_create_repo_duplicate(self, client: AsyncClient):
        data = {"name": "dup-repo", "full_name": "test/dup"}
        resp1 = await client.post("/api/v1/repositories", json=data)
        resp2 = await client.post("/api/v1/repositories", json=data)
        assert resp1.status_code == 201
        assert resp2.status_code in (201, 409, 500)

    async def test_get_repo_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/repositories/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_repo_not_found(self, client: AsyncClient):
        resp = await client.delete(f"/api/v1/repositories/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_get_repo_invalid_uuid(self, client: AsyncClient):
        resp = await client.get("/api/v1/repositories/not-a-uuid")
        assert resp.status_code in (400, 422)


class TestOrganizationEndpoints:
    async def test_list_orgs(self, client: AsyncClient):
        resp = await client.get("/api/v1/organizations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_org_invalid_slug(self, client: AsyncClient):
        resp = await client.post("/api/v1/organizations", json={
            "name": "Test",
            "slug": "INVALID SLUG",
        })
        assert resp.status_code == 422

    async def test_create_org_missing_name(self, client: AsyncClient):
        resp = await client.post("/api/v1/organizations", json={"slug": "test"})
        assert resp.status_code == 422

    async def test_get_org_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/organizations/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_org_not_found(self, client: AsyncClient):
        resp = await client.delete(f"/api/v1/organizations/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestChatEndpoints:
    async def test_chat_basic(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert "conversation_id" in body
        assert "confidence" in body

    async def test_chat_empty_message(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat", json={"message": ""})
        assert resp.status_code == 422

    async def test_chat_long_message(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat", json={"message": "x" * 5000})
        assert resp.status_code in (200, 422)

    async def test_chat_invalid_conversation(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat", json={
            "message": "Hello",
            "conversation_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 404

    async def test_chat_stream_endpoint(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat/stream", json={"message": "Hi"})
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")

    async def test_list_conversations(self, client: AsyncClient):
        resp = await client.get("/api/v1/chat/conversations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_conversation_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/chat/conversations/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestErrorHandling:
    async def test_not_found_structure(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/repositories/{uuid.uuid4()}")
        body = resp.json()
        assert "error" in body or "detail" in body

    async def test_validation_structure(self, client: AsyncClient):
        resp = await client.post("/api/v1/code/analyze", json={"content": "", "language": ""})
        body = resp.json()
        assert "error" in body or "detail" in body

    async def test_404_on_unknown_route(self, client: AsyncClient):
        resp = await client.get("/api/v1/nonexistent")
        assert resp.status_code == 404

    async def test_method_not_allowed(self, client: AsyncClient):
        resp = await client.put("/health")
        assert resp.status_code == 405

    async def test_large_payload_rejected(self, client: AsyncClient):
        resp = await client.post("/api/v1/code/analyze", json={
            "content": "x" * 600000,
            "language": "python",
        })
        assert resp.status_code in (413, 422)
