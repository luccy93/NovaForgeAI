"""RAG (Volume 43) test fixtures.

Self-contained: registers the RAG models on the shared ``Base``, creates the
tables against the test database, and provides DB / fake-embedding / user
fixtures. Disables the Redis cache in the retrieval service so tests never
depend on a running Redis.
"""

import os
import sys
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import configure_mappers

# Ensure a deterministic test DB before importing app code.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("TESTING", "true")

# Register the JSONB->JSON sqlite compile hook so RAG models (which use JSONB)
# can be created on SQLite.
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


# `backend` must be importable (the backend conftest also ensures this).
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, async_engine, async_session  # noqa: E402
from app.rag import models as _rag_models  # noqa: E402,F401  (registers rag tables)


class FakeEmbedding:
    """Deterministic fake embedding client for tests (no network/OpenAI)."""

    model = "fake"
    dimension = 8
    version = "fake@8"

    def __init__(self, *args, **kwargs):
        pass

    async def embed(self, texts):
        out = []
        for t in texts:
            h = hash(t) & 0xFFFFFFFF
            vec = [((h >> (i * 3)) & 7) / 7.0 - 0.5 for i in range(self.dimension)]
            out.append(vec)
        return out

    async def embed_one(self, text):
        return (await self.embed([text]))[0]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _tables():
    import app.rag.ingestion  # noqa: F401
    import app.rag.retrieval.service  # noqa: F401

    configure_mappers()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def fake_embedding():
    return FakeEmbedding()


@pytest.fixture
def user():
    return type("U", (), {"id": uuid4(), "organization_id": uuid4()})()


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    from app.rag.retrieval import service as svc

    async def _noop_get(*a, **k):
        return None

    async def _noop_set(*a, **k):
        return None

    monkeypatch.setattr(svc, "cache_get", _noop_get)
    monkeypatch.setattr(svc, "cache_set", _noop_set)
