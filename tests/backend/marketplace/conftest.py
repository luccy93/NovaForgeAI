"""Marketplace (Volume 44) test fixtures.

Mirrors the proven RAG conftest: uses the application's ``async_engine`` /
``async_session`` (bound to the test database by the backend conftest) and
creates all tables once per session, relying on per-test rollbacks for
isolation. API tests get a fresh table set per test via a ``client`` fixture.
"""

import os
import sys
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure a deterministic test DB before importing app code.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("TESTING", "true")

from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, async_engine, async_session, get_db  # noqa: E402
from app.marketplace import models as _mp  # noqa: E402,F401
from app.api.marketplace import router as marketplace_router  # noqa: E402
from app.api.auth import _get_current_user  # noqa: E402


class FakeUser:
    def __init__(self, org_id=None, user_id=None, is_admin=False):
        self.id = user_id or uuid4()
        self.organization_id = org_id or uuid4()
        self.is_superuser = is_admin


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def org_ids():
    return {"publisher": uuid4(), "installer": uuid4()}


@pytest.fixture
def user(org_ids):
    return FakeUser(org_id=org_ids["installer"], user_id=uuid4())


@pytest.fixture
def publisher_user(org_ids):
    return FakeUser(org_id=org_ids["publisher"], user_id=uuid4())


@pytest_asyncio.fixture
async def client(org_ids):
    # Fresh table set per API test to avoid cross-test pollution from commits.
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(marketplace_router)
    fake = FakeUser(org_id=org_ids["installer"], user_id=uuid4())

    async def _override_get_db():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = lambda: fake

    with TestClient(app) as c:
        yield c


def make_manifest(**overrides):
    base = {
        "name": "Demo Agent",
        "version": "1.0.0",
        "type": "agent",
        "entrypoint": "agent.main:run",
        "runtime": "python3.11",
        "permissions": ["model:use", "repository:read"],
        "tools": ["search", "read_file"],
        "models": ["gpt-4o"],
        "events": ["agent.run.completed"],
        "configuration": [
            {"key": "max_steps", "type": "integer", "required": False, "default": 10},
            {"key": "api_token", "type": "secret", "required": True},
        ],
        "dependencies": [],
        "environment": {},
        "resources": {"timeout_seconds": 300, "memory": "512Mi"},
        "compatibility": {},
        "security_requirements": {"autonomy": "low"},
        "description": "A demo agent package.",
        "license": "MIT",
        "tags": ["agents", "demo"],
        "category": "Agents",
    }
    base.update(overrides)
    return base


@pytest.fixture
def manifest():
    return make_manifest
