"""Shared fixtures for Security Platform tests (Volume 47).

Standalone conftest that avoids the full app import chain.
Pre-populates sys.modules["app"] as a stub so the root conftest's
``from app import create_app`` returns the stub without triggering
app/__init__.py.
"""

import importlib
import importlib.util
import os
import sys
import types

# ── Environment setup ──────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("TESTING", "true")

_BACKEND_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")
)
_APP_DIR = os.path.join(_BACKEND_ROOT, "app")


def _ensure_package(name: str, path: str) -> types.ModuleType:
    """Register or create a package module in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    pkg = types.ModuleType(name)
    pkg.__path__ = [path]
    pkg.__package__ = name
    sys.modules[name] = pkg
    return pkg


def _import_module_from_file(name: str, filepath: str) -> types.ModuleType:
    """Import a single module from a file, bypassing package __init__ chains."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Bootstrap: load core modules without triggering app/__init__.py ────
# Must run BEFORE the root tests/conftest.py tries ``from app import create_app``.

_ensure_package("app", _APP_DIR)
_ensure_package("app.core", os.path.join(_APP_DIR, "core"))
_ensure_package("app.api", os.path.join(_APP_DIR, "api"))
_ensure_package("app.security", os.path.join(_APP_DIR, "security"))

# Load core modules manually
_import_module_from_file("app.core.config", os.path.join(_APP_DIR, "core", "config.py"))
_import_module_from_file("app.core.database", os.path.join(_APP_DIR, "core", "database.py"))

# Load security models
_import_module_from_file("app.security.models", os.path.join(_APP_DIR, "security", "models.py"))

# Load the security router without triggering app.api.__init__
_security_router_mod = _import_module_from_file(
    "app.api.security",
    os.path.join(_APP_DIR, "api", "security.py"),
)

# Force mapper configuration
from sqlalchemy.orm import configure_mappers  # noqa: E402
configure_mappers()

# ── Now safe to import app modules ─────────────────────────────────────
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

if not hasattr(compiles, '_jsonb_compiled'):
    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(element, compiler, **kw):
        return "JSON"
    compiles._jsonb_compiled = True

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402

security_router = _security_router_mod.router

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _setup_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


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
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_setup_tables())

    app = FastAPI()
    app.include_router(security_router, prefix="/security")

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
