"""Release (Volume 56) test fixtures — DB-backed via test.db."""

import os
import sys
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("TESTING", "true")

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, async_engine, async_session, get_db
from app.release import models as _rel  # noqa
from app.delivery import models as _del  # noqa
from app.api.release import router as release_router
from app.api.release import feature_flag_router
from app.api.auth import _get_current_user


class FakeUser:
    def __init__(self, org_id=None, user_id=None):
        self.id = user_id or uuid4()
        self.organization_id = org_id or uuid4()
        self.is_superuser = False


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
def org_id():
    return uuid4()


@pytest.fixture
def user(org_id):
    return FakeUser(org_id=org_id, user_id=uuid4())


@pytest_asyncio.fixture
async def client():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    app = FastAPI()
    app.include_router(release_router)
    app.include_router(feature_flag_router)
    fake = FakeUser()

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
