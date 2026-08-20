"""Shared fixtures for Delivery Platform tests (Volume 46)."""

import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("TESTING", "true")

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, get_db
from app.delivery import models as _delivery_models  # noqa: F401
from app.api.delivery import router as delivery_router

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _SessionLocal() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client():
    loop = __import__("asyncio").new_event_loop()
    loop.run_until_complete(_setup_tables())

    app = FastAPI()
    app.include_router(delivery_router)

    async def _override_get_db():
        async with _SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c
    loop.close()


async def _setup_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
