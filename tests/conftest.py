"""Global test configuration and fixtures."""

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

# Test-environment configuration (must be set before any app import).
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_novaforge.db")
os.environ.setdefault("TESTING", "true")

from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app import create_app  # noqa: E402
from app.core.config import settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    """Create all tables on the SQLite test database once per session."""
    from app.core.database import Base, async_engine

    async def _init() -> None:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    yield
    asyncio.run(async_engine.dispose())
    if os.path.exists("./test_novaforge.db"):
        os.remove("./test_novaforge.db")


# ─── Pytest Configuration ──────────────────────────────────────────

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: marks tests that require external services (PG, Neo4j, etc.)")
    config.addinivalue_line("markers", "slow: marks slow tests (>5s)")
    config.addinivalue_line("markers", "ai_eval: marks AI evaluation tests")
    config.addinivalue_line("markers", "security: marks security tests")
    config.addinivalue_line("markers", "load: marks load/performance tests")
    config.addinivalue_line("markers", "e2e: marks end-to-end tests")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip slow, integration, load, e2e tests by default unless explicitly requested."""
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Slow test; run with --run-slow"))
        if "integration" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Integration test; requires external services"))
        if "load" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Load test; run separately"))
        if "e2e" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="E2E test; requires full stack"))


# ─── App & Client Fixtures ─────────────────────────────────────────

@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Client with valid JWT token for authenticated requests."""
    payload = {
        "email": "testuser@novaforge.ai",
        "username": "testuser",
        "password": "TestPass123!",
        "full_name": "Test User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    if resp.status_code == 201:
        data = resp.json()
        token = data.get("access_token", "")
    else:
        token = ""

    class AuthClientWrapper:
        def __init__(self, ac: AsyncClient, token: str):
            self._ac = ac
            self._token = token

        async def get(self, url: str, **kwargs):
            return await self._ac.get(url, headers=self._headers(), **kwargs)

        async def post(self, url: str, **kwargs):
            return await self._ac.post(url, headers=self._headers(), **kwargs)

        async def put(self, url: str, **kwargs):
            return await self._ac.put(url, headers=self._headers(), **kwargs)

        async def delete(self, url: str, **kwargs):
            return await self._ac.delete(url, headers=self._headers(), **kwargs)

        def _headers(self):
            h = {"Content-Type": "application/json"}
            if self._token:
                h["Authorization"] = f"Bearer {self._token}"
            return h

    yield AuthClientWrapper(client, token)


# ─── Mock Data ──────────────────────────────────────────────────────

@pytest.fixture
def sample_python_code() -> str:
    return """
import os
from typing import Optional

class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id: int) -> Optional[dict]:
        if user_id > 0:
            return {"id": user_id, "name": "Test"}
        return None

    def create_user(self, name: str, email: str) -> dict:
        user = {"id": 1, "name": name, "email": email}
        return user
"""


@pytest.fixture
def sample_typescript_code() -> str:
    return """
import { Component, OnInit } from '@angular/core';

export class AppComponent implements OnInit {
  title = 'novaforge';

  constructor() {
    console.log('App initialized');
  }

  ngOnInit(): void {
    this.loadData();
  }

  private loadData(): Promise<void> {
    return Promise.resolve();
  }
}
"""


@pytest.fixture
def sample_go_code() -> str:
    return """
package main

import (
    "fmt"
    "net/http"
)

func main() {
    http.HandleFunc("/", handler)
    http.ListenAndServe(":8080", nil)
}

func handler(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintf(w, "Hello, NovaForge!")
}
"""


@pytest.fixture
def sample_rust_code() -> str:
    return """
use std::collections::HashMap;

struct Config {
    host: String,
    port: u16,
}

fn main() {
    let config = Config {
        host: String::from("localhost"),
        port: 8080,
    };
    println!("Server starting on {}:{}", config.host, config.port);
}

fn calculate(items: &[i32]) -> i32 {
    items.iter().sum()
}
"""


@pytest.fixture
def sample_java_code() -> str:
    return """
import java.util.List;
import java.util.ArrayList;

public class NovaForgeApplication {
    private String name;
    private List<String> features;

    public NovaForgeApplication(String name) {
        this.name = name;
        this.features = new ArrayList<>();
    }

    public void addFeature(String feature) {
        this.features.add(feature);
    }

    public List<String> getFeatures() {
        return this.features;
    }

    public static void main(String[] args) {
        NovaForgeApplication app = new NovaForgeApplication("NovaForge");
        app.addFeature("AI");
        System.out.println(app.name);
    }
}
"""


# ─── Mock Service Fixtures ─────────────────────────────────────────

@pytest.fixture
def mock_embedding_service():
    """Mock embedding service returning fixed vectors."""
    with patch("app.services.embeddings.EmbeddingService") as mock:
        instance = mock.return_value
        instance.get_embeddings.return_value = [[0.1] * 384]
        instance.get_embedding.return_value = [0.1] * 384
        yield instance


@pytest.fixture
def mock_vector_store():
    """Mock vector store returning sample results."""
    with patch("app.services.vector_store.VectorStoreService") as mock:
        instance = mock.return_value
        instance.search.return_value = [
            {"id": "1", "score": 0.95, "payload": {"content": "Sample code", "file_path": "main.py"}},
            {"id": "2", "score": 0.85, "payload": {"content": "More code", "file_path": "utils.py"}},
        ]
        yield instance


@pytest.fixture
def mock_graph_store():
    """Mock graph store returning sample results."""
    with patch("app.services.graph_store.GraphStoreService") as mock:
        instance = mock.return_value
        instance.search_by_embedding.return_value = [
            {"content": "Graph result", "file_path": "graph.py", "score": 0.9},
        ]
        instance.get_code_graph.return_value = {
            "nodes": [{"id": "1", "file_path": "main.py", "language": "python"}],
            "relationships": [],
        }
        yield instance


@pytest.fixture
def mock_llm_client():
    """Mock LLM client returning fixed responses."""
    with patch("app.services.rag_pipeline.RAGPipeline._init_llm") as mock:
        instance = MagicMock()
        instance.chat.return_value = {"choices": [{"message": {"content": "Mock answer"}}]}
        mock.return_value = None
        yield instance
