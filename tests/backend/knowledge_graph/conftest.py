"""Standalone conftest for Volume 51 Knowledge Graph Platform tests."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import JSON

_BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
_APP_DIR = _BACKEND_ROOT / "app"


def _ensure_package(name: str, path: Path | None = None):
    mod = type(sys)(name)
    mod.__path__ = [str(path)] if path else []
    mod.__package__ = name
    mod.__loader__ = None
    sys.modules.setdefault(name, mod)


def _import_module_from_file(name: str, filepath: Path):
    spec = importlib.util.spec_from_file_location(name, str(filepath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    _ensure_package("app", _APP_DIR)
    _ensure_package("app.core", _APP_DIR / "core")
    _ensure_package("app.api", _APP_DIR / "api")
    _ensure_package("app.knowledge_graph", _APP_DIR / "knowledge_graph")
    _ensure_package("app.cli", _APP_DIR / "cli")

    _import_module_from_file("app.core.config", _APP_DIR / "core" / "config.py")
    _import_module_from_file("app.core.database", _APP_DIR / "core" / "database.py")
    _import_module_from_file("app.knowledge_graph.constants", _APP_DIR / "knowledge_graph" / "constants.py")
    _import_module_from_file("app.knowledge_graph.config", _APP_DIR / "knowledge_graph" / "config.py")
    _import_module_from_file("app.knowledge_graph.models", _APP_DIR / "knowledge_graph" / "models.py")
    _import_module_from_file("app.knowledge_graph.schemas", _APP_DIR / "knowledge_graph" / "schemas.py")

    for name in ("entity_service", "relationship_service", "search_service",
                 "traversal_service", "entity_resolution_service",
                 "temporal_service", "evidence_service", "quality_service",
                 "health_service", "indexing_service", "neo4j_service"):
        filepath = _APP_DIR / "knowledge_graph" / f"{name}.py"
        if filepath.exists():
            _import_module_from_file(f"app.knowledge_graph.{name}", filepath)

    _import_module_from_file("app.knowledge_graph.__init__", _APP_DIR / "knowledge_graph" / "__init__.py")
    _import_module_from_file("app.api.knowledge_graph", _APP_DIR / "api" / "knowledge_graph.py")

    from sqlalchemy.orm import configure_mappers
    configure_mappers()


_bootstrap()


@compiles(JSON, "sqlite")
def compile_json_sqlite(type_, compiler, **kw):
    return "JSON"


DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture()
async def db():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    from app.core.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
def entity_svc():
    from app.knowledge_graph.entity_service import EntityService
    return EntityService()


@pytest.fixture()
def rel_svc():
    from app.knowledge_graph.relationship_service import RelationshipService
    return RelationshipService()


@pytest.fixture()
def sample_entity():
    return {"tenant": "test", "entity_type": "repository", "name": "my-repo",
            "display_name": "My Repository", "description": "A test repo",
            "external_id": "repo-123", "provider": "github"}
