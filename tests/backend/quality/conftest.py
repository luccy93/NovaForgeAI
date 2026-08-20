"""Standalone conftest for Volume 48 Quality Engine tests.

Avoids the full app import chain. Pre-registers SQLAlchemy models,
creates an in-memory SQLite DB, and overrides FastAPI dependencies.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import JSON

# ---------- path setup --------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
_APP_DIR = _BACKEND_ROOT / "app"

# ---------- stub helpers ------------------------------------------------
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


# ---------- bootstrap ---------------------------------------------------
def _bootstrap():
    _ensure_package("app", _APP_DIR)
    _ensure_package("app.core", _APP_DIR / "core")
    _ensure_package("app.api", _APP_DIR / "api")
    _ensure_package("app.quality", _APP_DIR / "quality")
    _ensure_package("app.quality.analyzers", _APP_DIR / "quality" / "analyzers")

    _import_module_from_file("app.core.config", _APP_DIR / "core" / "config.py")
    _import_module_from_file("app.core.database", _APP_DIR / "core" / "database.py")
    _import_module_from_file("app.quality.models", _APP_DIR / "quality" / "models.py")

    _import_module_from_file("app.quality.schemas", _APP_DIR / "quality" / "schemas.py")
    _import_module_from_file("app.quality.config", _APP_DIR / "quality" / "config.py")
    _import_module_from_file("app.quality.finding_model", _APP_DIR / "quality" / "finding_model.py")
    _import_module_from_file("app.quality.risk_scorer", _APP_DIR / "quality" / "risk_scorer.py")
    _import_module_from_file("app.quality.dedup", _APP_DIR / "quality" / "dedup.py")
    _import_module_from_file("app.quality.correlation", _APP_DIR / "quality" / "correlation.py")
    _import_module_from_file("app.quality.gates", _APP_DIR / "quality" / "gates.py")
    _import_module_from_file("app.quality.baseline", _APP_DIR / "quality" / "baseline.py")
    _import_module_from_file("app.quality.review_service", _APP_DIR / "quality" / "review_service.py")
    _import_module_from_file("app.quality.report_service", _APP_DIR / "quality" / "report_service.py")
    _import_module_from_file("app.quality.diff_parser", _APP_DIR / "quality" / "diff_parser.py")
    _import_module_from_file("app.quality.context_retrieval", _APP_DIR / "quality" / "context_retrieval.py")
    _import_module_from_file("app.quality.remediation", _APP_DIR / "quality" / "remediation.py")
    _import_module_from_file("app.quality.test_generation", _APP_DIR / "quality" / "test_generation.py")
    _import_module_from_file("app.quality.historical", _APP_DIR / "quality" / "historical.py")
    _import_module_from_file("app.quality.prompt_versioning", _APP_DIR / "quality" / "prompt_versioning.py")
    _import_module_from_file("app.quality.cost_tracker", _APP_DIR / "quality" / "cost_tracker.py")

    for name in ("base", "correctness", "performance", "reliability", "architecture",
                 "api_compat", "database", "dependency", "documentation", "dead_code",
                 "test_quality", "ai_review", "code_smells"):
        filepath = _APP_DIR / "quality" / "analyzers" / f"{name}.py"
        if filepath.exists():
            _import_module_from_file(f"app.quality.analyzers.{name}", filepath)

    _init = _import_module_from_file("app.quality.analyzers", _APP_DIR / "quality" / "analyzers" / "__init__.py")

    _pkg = _import_module_from_file("app.quality", _APP_DIR / "quality" / "__init__.py")

    _import_module_from_file("app.quality.pipeline", _APP_DIR / "quality" / "pipeline.py")

    _import_module_from_file("app.api.quality", _APP_DIR / "api" / "quality.py")

    from sqlalchemy.orm import configure_mappers
    configure_mappers()


_bootstrap()

# ---------- SQLite JSONB compile hook ------------------------------------
try:
    @compiles(JSON, "sqlite")
    def compile_json_sqlite(type_, compiler, **kw):
        return "JSON"
except Exception:
    pass

# ---------- fixtures ----------------------------------------------------
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
    from app.api.quality import router as quality_router
    from app.core.database import get_db

    app = FastAPI()
    app.include_router(quality_router, prefix="/quality")

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)
