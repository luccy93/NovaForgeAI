"""Standalone conftest for Volume 50 Analytics Platform tests."""

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
    _ensure_package("app.analytics", _APP_DIR / "analytics")
    _ensure_package("app.cli", _APP_DIR / "cli")

    _import_module_from_file("app.core.config", _APP_DIR / "core" / "config.py")
    _import_module_from_file("app.core.database", _APP_DIR / "core" / "database.py")
    _import_module_from_file("app.analytics.constants", _APP_DIR / "analytics" / "constants.py")
    _import_module_from_file("app.analytics.config", _APP_DIR / "analytics" / "config.py")
    _import_module_from_file("app.analytics.models", _APP_DIR / "analytics" / "models.py")
    _import_module_from_file("app.analytics.schemas", _APP_DIR / "analytics" / "schemas.py")

    for name in ("normalization_service", "aggregation_service", "cost_service",
                 "budget_service", "alert_service", "report_service",
                 "forecasting_service", "recommendation_service",
                 "slo_analytics_service", "engineering_service",
                 "ai_analytics_service", "marketplace_analytics_service",
                 "security_analytics_service", "data_quality_service"):
        filepath = _APP_DIR / "analytics" / f"{name}.py"
        if filepath.exists():
            _import_module_from_file(f"app.analytics.{name}", filepath)

    _import_module_from_file("app.analytics.__init__", _APP_DIR / "analytics" / "__init__.py")
    _import_module_from_file("app.api.analytics", _APP_DIR / "api" / "analytics.py")

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
def sample_event():
    return {
        "tenant": "test",
        "source": "pytest",
        "event_type": "test.event",
        "event_timestamp": "2026-01-01T00:00:00Z",
        "cost_usd": 0.05,
        "duration_ms": 100.0,
    }


@pytest.fixture()
def sample_cost():
    return {
        "tenant": "test",
        "cost_type": "ai_model",
        "amount_usd": 1.50,
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "model": "gpt-4",
        "provider": "openai",
        "agent": "coder",
    }


@pytest.fixture()
def sample_budget():
    return {
        "tenant": "test",
        "name": "Monthly AI Budget",
        "scope": "organization",
        "scope_value": "test-org",
        "limit_usd": 1000.0,
        "cost_type": "total",
        "period": "monthly",
    }


@pytest.fixture()
def sample_metric_query():
    return {
        "metric_name": "ai.calls.count",
        "granularity": "hour",
        "dimensions": {"model": "gpt-4"},
    }


@pytest.fixture()
def sample_report():
    return {
        "tenant": "test",
        "report_type": "executive",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
    }


@pytest.fixture()
def sample_forecast():
    return {
        "tenant": "test",
        "metric_name": "ai.cost.total",
        "horizon_days": 30,
    }
