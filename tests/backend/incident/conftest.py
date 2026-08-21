"""Standalone conftest for Volume 49 Incident Response Platform tests."""

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
    _ensure_package("app.incident", _APP_DIR / "incident")
    _ensure_package("app.cli", _APP_DIR / "cli")

    _import_module_from_file("app.core.config", _APP_DIR / "core" / "config.py")
    _import_module_from_file("app.core.database", _APP_DIR / "core" / "database.py")
    _import_module_from_file("app.incident.constants", _APP_DIR / "incident" / "constants.py")
    _import_module_from_file("app.incident.config", _APP_DIR / "incident" / "config.py")
    _import_module_from_file("app.incident.models", _APP_DIR / "incident" / "models.py")
    _import_module_from_file("app.incident.schemas", _APP_DIR / "incident" / "schemas.py")

    for name in ("alert_service", "incident_service", "correlation_service",
                 "change_correlation", "investigation_agent", "root_cause_service",
                 "triage_service", "timeline_service", "remediation_engine",
                 "runbook_engine", "escalation_manager", "anomaly_detector",
                 "ai_incident_detector", "recurrence_detector", "incident_memory",
                 "reliability_metrics", "health_service"):
        filepath = _APP_DIR / "incident" / f"{name}.py"
        if filepath.exists():
            _import_module_from_file(f"app.incident.{name}", filepath)

    _import_module_from_file("app.incident.__init__", _APP_DIR / "incident" / "__init__.py")
    _import_module_from_file("app.api.incident", _APP_DIR / "api" / "incident.py")

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
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
def client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.incident import router as incident_router
    from app.core.database import get_db

    app = FastAPI()
    app.include_router(incident_router, prefix="/incident")

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)
