"""Test generation and execution across existing CI — Volume 67 Commit 1.

Test plans are deterministic proposals derived from real code (function
/class names extracted from the patch). Execution triggers a real
delivery pipeline run (honest CI artifact) and never fabricates
pass/fail results — outcomes come only from recorded CI results.
"""

import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import (
    DEFAULT_TEST_FRAMEWORK,
    NotFoundError,
    _as_uuid,
    emit_event,
    resolve_repository,
)
from app.ai_dev.models import CodeTestRun
from app.ai_dev.patch import get_patch

logger = logging.getLogger(__name__)

_MAX_PLAN_SOURCE_FILES = 10
_MAX_TESTS_PER_FILE = 20
_FUNC_RE = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _proposed_test_path(source_path: str) -> str:
    if source_path.endswith(".py"):
        base = source_path[:-3]
        return f"tests/test_{base.split('/')[-1]}.py"
    return f"tests/test_{source_path.replace('/', '_')}.txt"


def _test_skeleton(name: str) -> str:
    return (
        f"def test_{name}_basic():\n"
        f"    # proposed test exercising {name}\n"
        f"    pass\n"
    )


def _extract_definitions(content: str) -> list[str]:
    names = []
    for line in (content or "").splitlines():
        m = _FUNC_RE.match(line.strip())
        if m and not m.group(1).startswith("_"):
            names.append(m.group(1))
    return names


async def generate_test_plan(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    repository_id,
    patch_id=None,
    commit_sha: Optional[str] = None,
    branch: Optional[str] = None,
    framework: Optional[str] = None,
) -> CodeTestRun:
    repo = await resolve_repository(db, tenant, repository_id)
    patch = None
    if patch_id:
        patch = await get_patch(db, tenant, patch_id)
        if patch.repository_id != repo.id:
            raise ValueError("patch does not belong to repository")

    source_files = []
    if patch:
        source_files = [
            {"path": f["path"], "content": f.get("new_content", "")}
            for f in (patch.files or [])
        ]
    else:
        for path in ["app/main.py", "app/service.py", "lib/core.py"]:
            source_files.append({"path": path, "content": ""})
    source_files = source_files[: _MAX_PLAN_SOURCE_FILES]

    framework = framework or DEFAULT_TEST_FRAMEWORK
    command = "pytest -q" if framework == "pytest" else f"{framework} test"

    test_plan = []
    for entry in source_files:
        defs = _extract_definitions(entry.get("content", ""))[:_MAX_TESTS_PER_FILE]
        test_plan.append(
            {
                "source_file": entry["path"],
                "proposed_test_file": _proposed_test_path(entry["path"]),
                "function_count": len(defs),
                "functions": defs,
                "skeleton": "\n".join(
                    _test_skeleton(d) if d else "# no public functions to exercise"
                    for d in defs[:5]
                ),
            }
        )

    run = CodeTestRun(
        tenant=tenant,
        repository_id=repo.id,
        branch=branch or repo.default_branch,
        commit_sha=commit_sha,
        patch_id=patch_id,
        status="GENERATED",
        framework=framework,
        command=command,
        test_plan=test_plan,
        model="template",
        created_by=user_id,
    )
    db.add(run)
    await db.flush()
    await emit_event(
        "CodeTestPlanned",
        {
            "run_id": str(run.id),
            "repository_id": str(repo.id),
            "framework": framework,
            "proposed_files": len(test_plan),
        },
        tenant,
    )
    return run


async def execute_tests(
    db: AsyncSession, tenant: str, user_id: str, run_id
) -> CodeTestRun:
    run = await db.get(CodeTestRun, _as_uuid(run_id))
    if run is None or run.tenant != tenant:
        raise NotFoundError("test run not found")
    if run.status != "GENERATED":
        raise ValueError(f"only GENERATED runs can execute (status={run.status})")

    try:
        from app.delivery.pipeline_service import PipelineService

        svc = PipelineService(db)
        pipelines, _ = await svc.list_pipelines(
            tenant=tenant, project="ai-dev-tests", repository=str(run.repository_id), limit=1
        )
        if pipelines:
            pipeline = pipelines[0]
        else:
            pipeline = await svc.create(
                tenant=tenant,
                project="ai-dev-tests",
                repository=str(run.repository_id),
                branch=run.branch or "main",
                name="ai-dev-unit-tests",
                stages=["test"],
            )
        delivery_run = await svc.trigger_run(
            pipeline.id,
            commit_sha=run.commit_sha or "",
            trigger="manual",
            actor=user_id,
            context={"ai_dev_test_run": str(run.id)},
        )
        await svc.add_job(
            delivery_run.id,
            stage="test",
            name="ai-dev-unit-tests",
            commands=(run.command or "pytest").split(";"),
        )
        run.ci_pipeline_run_id = str(delivery_run.id)
        run.status = "QUEUED"
        await db.flush()
        await emit_event(
            "CodeTestExecuted",
            {
                "run_id": str(run.id),
                "repository_id": str(run.repository_id),
                "delivery_run_id": str(delivery_run.id),
                "status": run.status,
            },
            tenant,
        )
        return run
    except Exception as exc:
        logger.warning("test execution trigger failed: %s", exc)
        run.status = "ERROR"
        await db.flush()
        raise


async def record_test_result(
    db: AsyncSession,
    tenant: str,
    run_id,
    status: str,
    *,
    results: Optional[list] = None,
    logs: Optional[str] = None,
    failures_analysis: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> CodeTestRun:
    run = await db.get(CodeTestRun, _as_uuid(run_id))
    if run is None or run.tenant != tenant:
        raise NotFoundError("test run not found")
    status = (status or "").upper()
    if status not in ("PASSED", "FAILED", "ERROR"):
        raise ValueError(f"invalid test status: {status}")
    run.status = status
    if results is not None:
        run.test_results = results
    if logs is not None:
        run.logs = logs
    if failures_analysis is not None:
        run.failures_analysis = failures_analysis
    if duration_ms is not None:
        run.duration_ms = duration_ms
    await db.flush()
    await emit_event(
        "CodeTestCompleted",
        {
            "run_id": str(run.id),
            "repository_id": str(run.repository_id),
            "status": status,
            "duration_ms": duration_ms,
            "test_count": len(results or []),
        },
        tenant,
    )
    return run


async def get_test_run(db: AsyncSession, tenant: str, run_id) -> CodeTestRun:
    run = await db.get(CodeTestRun, _as_uuid(run_id))
    if run is None or run.tenant != tenant:
        raise NotFoundError("test run not found")
    return run