"""Volume 43 — RAG API integration tests (full router wiring)."""

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.auth import _get_current_user
from app.api.rag_api import configure_rag, router
from app.core.database import async_session, get_db


@pytest.fixture
def app_instance(fake_embedding):
    from app.api import rag_api

    rag_api._rag_service = None
    configure_rag(fake_embedding, None)

    app = FastAPI()
    app.include_router(router)

    uid = uuid.uuid4()
    oid = uuid.uuid4()
    user = type("U", (), {"id": uid, "organization_id": oid})()

    async def _override_db():
        async with async_session() as session:
            yield session

    def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[_get_current_user] = _override_user
    return app


@pytest_asyncio.fixture
async def client(app_instance):
    app = app_instance
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_and_index_and_search(client):
    r = await client.post(
        "/rag/sources",
        json={"name": "api-doc", "source_type": "documentation", "content": "APISEARCH_omega_8821 welcome guide"},
    )
    assert r.status_code in (200, 201), r.text
    source_id = r.json()["id"]

    r = await client.post(f"/rag/sources/{source_id}/index", json={"content": "APISEARCH_omega_8821 welcome guide"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("validated", "indexed")

    r = await client.post("/rag/search", json={"query": "APISEARCH_omega_8821", "limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answerability"] != "INSUFFICIENT"
    assert any("APISEARCH_omega_8821" in (c.get("content") or "") for c in body.get("chunks", []))


@pytest.mark.asyncio
async def test_list_and_health(client):
    r = await client.get("/rag/sources")
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = await client.get("/rag/health")
    assert r.status_code == 200
    assert "stale_count" in r.json() or "source_counts" in r.json() or "chunk_count" in r.json()


@pytest.mark.asyncio
async def test_search_insufficient_returns_200(client):
    r = await client.post("/rag/search", json={"query": "zzz_nomatch_quantum_xyz_4455_qqq"})
    assert r.status_code == 200
    assert r.json()["answerability"] == "INSUFFICIENT"
