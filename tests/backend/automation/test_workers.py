"""Tests for engine workers: planner, coder, tester, reviewer, security, devops."""

import pytest
from app.automation.engine_workers import (
    PlannerWorker, CoderWorker, TesterWorker,
    ReviewerWorker, SecurityWorker, DevOpsWorker,
    get_worker, list_workers,
)


@pytest.mark.asyncio
async def test_planner_worker_basic():
    w = PlannerWorker()
    result = await w.execute({
        "request": "fix login bug",
        "task_type": "bug",
        "repository": "r1",
        "branch": "main",
    })
    assert result.success is True
    assert "objective" in result.output
    assert "Fix" in result.output["objective"]


@pytest.mark.asyncio
async def test_planner_worker_feature():
    w = PlannerWorker()
    result = await w.execute({
        "request": "add user dashboard",
        "task_type": "feature",
        "repository": "r1",
    })
    assert "Implement" in result.output["objective"]
    assert "feature" in result.output["required_tools"] or "search_code" in result.output["required_tools"]


@pytest.mark.asyncio
async def test_planner_worker_security_risk():
    w = PlannerWorker()
    result = await w.execute({
        "request": "fix authentication vulnerability",
        "task_type": "security",
        "repository": "r1",
    })
    risks = result.output["risks"]
    assert any("security" in r.lower() for r in risks)


@pytest.mark.asyncio
async def test_coder_worker():
    w = CoderWorker()
    result = await w.execute({
        "plan": {
            "objective": "Fix bug",
            "files": ["app.py", "test_app.py"],
        },
    })
    assert result.success is True
    assert result.output["files_changed"] == 2
    assert "diff" in result.output


@pytest.mark.asyncio
async def test_tester_worker():
    w = TesterWorker()
    result = await w.execute({
        "patch": {"files_changed": 3},
    })
    assert result.success is True
    assert result.output["tests_total"] == 6
    assert result.output["tests_passed"] == 6
    assert result.output["tests_failed"] == 0


@pytest.mark.asyncio
async def test_reviewer_worker_clean():
    w = ReviewerWorker()
    result = await w.execute({
        "patch": {"files_changed": 3, "reason": "fix bug"},
    })
    assert result.success is True
    assert result.output["overall_score"] >= 0.6


@pytest.mark.asyncio
async def test_reviewer_worker_large_change():
    w = ReviewerWorker()
    result = await w.execute({
        "patch": {"files_changed": 20, "reason": "big refactor"},
    })
    findings = result.output["findings"]
    assert any("Large change" in f["message"] for f in findings)


@pytest.mark.asyncio
async def test_security_worker_clean():
    w = SecurityWorker()
    result = await w.execute({
        "patch": {"diff": "normal diff", "file_changes": []},
    })
    assert result.success is True


@pytest.mark.asyncio
async def test_security_worker_finds_secrets():
    w = SecurityWorker()
    result = await w.execute({
        "patch": {"diff": 'password = "secret123"', "file_changes": []},
    })
    assert result.success is False
    assert result.output["blocks_delivery"] is True


@pytest.mark.asyncio
async def test_devops_worker():
    w = DevOpsWorker()
    result = await w.execute({
        "action": "deploy",
        "environment": "staging",
        "commit_sha": "abc123",
    })
    assert result.success is True
    assert result.output["action"] == "deploy"


@pytest.mark.asyncio
async def test_get_worker():
    assert isinstance(get_worker("planner"), PlannerWorker)
    assert isinstance(get_worker("coder"), CoderWorker)
    assert isinstance(get_worker("tester"), TesterWorker)
    assert isinstance(get_worker("reviewer"), ReviewerWorker)
    assert isinstance(get_worker("security"), SecurityWorker)
    assert isinstance(get_worker("devops"), DevOpsWorker)
    assert get_worker("nonexistent") is None


def test_list_workers():
    workers = list_workers()
    assert "planner" in workers
    assert "coder" in workers
    assert "tester" in workers
    assert "reviewer" in workers
    assert "security" in workers
    assert "devops" in workers
    assert len(workers) == 6
