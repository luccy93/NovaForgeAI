import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app import create_app

app = create_app()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


pytestmark = pytest.mark.asyncio


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_readiness_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "checks" in data
    assert "app" in data["checks"]


async def test_root_not_found(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 404


async def test_cors_headers(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"


async def test_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers


async def test_response_time_header(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert "X-Response-Time-Ms" in response.headers


async def test_list_agents_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    agent_names = {a["name"] for a in data}
    assert "code_reviewer" in agent_names
    assert "tester" in agent_names
    assert "documenter" in agent_names
    assert "explainer" in agent_names
    assert "refactorer" in agent_names


async def test_analyze_code_python(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/code/analyze",
        json={
            "content": "def hello():\n    return 'world'\n",
            "language": "python",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "python"
    assert data["line_count"] == 2
    assert len(data["functions"]) >= 1
    assert data["functions"][0]["name"] == "hello"


async def test_analyze_code_unsupported_language(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/code/analyze",
        json={"content": "foo", "language": "brainfuck"},
    )
    assert response.status_code == 422


async def test_extract_functions(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/code/functions",
        json={
            "content": "def foo(x): pass\ndef bar(y): pass\n",
            "language": "python",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["functions"]) >= 2
    names = [f["name"] for f in data["functions"]]
    assert "foo" in names
    assert "bar" in names


async def test_compute_complexity(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/code/complexity",
        json={"content": "if x:\n    if y:\n        pass\n", "language": "python"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cyclomatic_complexity"] >= 3
    assert data["language"] == "python"


async def test_detect_dependencies(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/code/dependencies",
        json={"content": "import os\nimport sys\nfrom datetime import datetime\n", "language": "python"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "os" in data["dependencies"]
    assert "sys" in data["dependencies"]


@pytest.mark.skip(reason="Requires running PostgreSQL")
async def test_register_validation(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "", "username": "", "password": ""},
    )
    assert response.status_code == 422


@pytest.mark.skip(reason="Requires running PostgreSQL")
async def test_login_validation(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": ""},
    )
    assert response.status_code == 401


async def test_not_found_error_format(client: AsyncClient) -> None:
    response = await client.get("/api/v1/repositories/nonexistent-id")
    assert response.status_code in (400, 404)
    body = response.json()
    assert "detail" in body or "error" in body


@pytest.mark.skip(reason="Requires running PostgreSQL")
async def test_chat_invalid_conversation(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"message": "hello", "conversation_id": "invalid-uuid"},
    )
    assert response.status_code == 400


@pytest.mark.skip(reason="Requires running PostgreSQL")
async def test_chat_missing_message(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"message": "", "conversation_id": None, "repo_id": None},
    )
    assert response.status_code == 422
