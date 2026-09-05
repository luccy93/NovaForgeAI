"""Production readiness gates — Volume 72 Commit 2.

N+1 query guards, evaluation latency bounds, observability surface
verification, SDK/API consistency and the machine/human readiness
report. Bounded and deterministic; no external services required.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event, select

from app.governance.plane_bindings import create_binding
from app.governance.plane_evaluate import evaluate
from app.governance.plane_policies import (
    create_policy,
    create_version,
    set_version_status,
)


def _allow_rule(value="read"):
    return {"name": "a", "effect": "allow", "priority": 1,
            "condition": {"field": "operation", "op": "equals", "value": value},
            "obligations": []}


async def _active_policy(db, org_id, value="read"):
    policy = await create_policy(db, org_id, f"perf-{uuid.uuid4().hex[:6]}")
    version = await create_version(db, org_id, policy["id"], [_allow_rule(value)])
    await set_version_status(db, org_id, version["id"], "ACTIVE")
    await create_binding(db, org_id, policy["id"], version["id"], scope_type="tenant")
    return policy


@pytest.mark.asyncio
async def test_evaluate_query_count_bounded(db, org_id):
    from app.core.database import async_engine
    await _active_policy(db, org_id)
    statements: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(async_engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        await evaluate(db, org_id, scope_type="tenant", operation="read",
                       context={"operation": "read"})
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    assert len(statements) <= 25, f"N+1 risk: {len(statements)} statements for one evaluation"


@pytest.mark.asyncio
async def test_evaluate_latency_bounded(db, org_id):
    await _active_policy(db, org_id)
    started = time.monotonic()
    for _ in range(20):
        await evaluate(db, org_id, scope_type="tenant", operation="read",
                       context={"operation": "read"})
    elapsed = time.monotonic() - started
    assert elapsed < 60.0, f"20 evaluations took {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_knowledge_search_bounded(db, org_id):
    from app.knowledge.retrieval import lexical_search
    started = time.monotonic()
    results = await lexical_search(db, org_id, "performance probe query terms here")
    elapsed = time.monotonic() - started
    assert isinstance(results, list)
    assert elapsed < 30.0


def test_observability_surface():
    from app.core.logging import get_logger
    from app.sre.metrics import render_metrics
    from app.sre.health import health_checker
    from app.observability.platform import platform_service

    assert get_logger("novaforge.readiness") is not None
    assert callable(render_metrics)
    for method in ("liveness", "readiness", "dependencies"):
        assert callable(getattr(health_checker, method)), method
    for method in ("ingest_metric", "ingest_log", "ingest_trace"):
        assert callable(getattr(platform_service, method)), method


def test_sdk_api_consistency():
    from app.api import create_app
    spec = create_app().openapi()
    paths = set(spec.get("paths", {}).keys())
    assert len(paths) > 1000
    expected = {
        "/api/v1/finops/usage/summary": "FinOpsMixin",
        "/api/v1/finops/budgets": "FinOpsMixin",
        "/api/v1/governance/policies": "GovernanceMixin",
        "/api/v1/governance/evaluate": "GovernanceMixin",
        "/api/v1/integrations": "IntegrationMixin",
        "/api/v1/integrations/oauth/start": "IntegrationMixin",
        "/api/v1/knowledge/search": "KnowledgeMixin",
        "/api/v1/workflows": "WorkflowMixin",
        "/api/v1/ai-dev/usage": "AIDevMixin",
        "/api/v1/observability/metrics": "ObservabilityMixin",
        "/api/v1/billing/plans": "BillingMixin",
    }
    for path, mixin in expected.items():
        assert any(p == path or p.startswith(path + "/") or p.startswith(path + "?")
                   for p in paths), f"{mixin} path missing: {path}"


def test_cli_handlers_registered():
    from app.cli import finops_commands, governance_commands, integrations_commands
    from app.novaforge_cli import NovaForgeCLI  # noqa: F401
    import inspect
    source = inspect.getsource(__import__("app.novaforge_cli", fromlist=["x"]))
    for cmd in ("finops", "governance", "integrations", "knowledge", "workflow"):
        assert f'cmd == "{cmd}"' in source, f"CLI dispatch missing: {cmd}"
    assert callable(finops_commands.handle_finops_command)
    assert callable(governance_commands.handle_governance_command)
    assert callable(integrations_commands.handle_integrations_command)


def test_readiness_report(tmp_path=None):
    import os
    import tempfile
    from app.platform_readiness import collect_readiness, write_report

    report = collect_readiness()
    assert report["status"] in ("READY", "READY_WITH_WARNINGS", "BLOCKED")
    assert report["migration"]["head"] == "0045_rename_enterprise_connection"
    assert report["migration"]["single_head"] is True
    assert report["routes"]["total"] > 1000
    assert report["events"]["total"] == report["events"]["unique_names"]
    outdir = tempfile.mkdtemp(prefix="readiness_")
    written = write_report(outdir)
    assert written["status"] == report["status"]
    assert os.path.exists(os.path.join(outdir, "readiness_report.json"))
    assert os.path.exists(os.path.join(outdir, "readiness_report.md"))
