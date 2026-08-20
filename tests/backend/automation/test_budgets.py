"""Tests for budget tracking and enforcement."""

import pytest
from app.automation.task_service import TaskService
from app.automation.budget_service import BudgetService
from app.automation.schemas import TaskCreate


@pytest.mark.asyncio
async def test_get_or_create_budget(db):
    svc = BudgetService(db)
    budget = await svc.get_or_create("tenant1")
    assert budget.tenant == "tenant1"
    assert budget.max_tokens == 1_000_000
    assert budget.used_tokens == 0


@pytest.mark.asyncio
async def test_idempotent_get(db):
    svc = BudgetService(db)
    b1 = await svc.get_or_create("tenant1")
    b2 = await svc.get_or_create("tenant1")
    assert b1.id == b2.id


@pytest.mark.asyncio
async def test_update_limits(db):
    svc = BudgetService(db)
    budget = await svc.update_limits("tenant1", max_tokens=500_000, max_cost_usd=10.0)
    assert budget.max_tokens == 500_000
    assert budget.max_cost_usd == 10.0


@pytest.mark.asyncio
async def test_record_usage(db):
    svc = BudgetService(db)
    budget = await svc.record_usage("tenant1", tokens=1000, tool_calls=5, cost_usd=0.5)
    assert budget.used_tokens == 1000
    assert budget.used_tool_calls == 5
    assert budget.used_cost_usd == 0.5


@pytest.mark.asyncio
async def test_check_budget_within(db):
    svc = BudgetService(db)
    await svc.record_usage("tenant1", tokens=100, cost_usd=0.01)
    result = await svc.check_budget("tenant1", estimated_tokens=100, estimated_cost=0.01)
    assert result["within_budget"] is True


@pytest.mark.asyncio
async def test_check_budget_exceeded_tokens(db):
    svc = BudgetService(db)
    budget = await svc.update_limits("tenant1", max_tokens=100)
    await svc.record_usage("tenant1", tokens=90)
    result = await svc.check_budget("tenant1", estimated_tokens=20)
    assert result["within_budget"] is False
    assert len(result["violations"]) >= 1


@pytest.mark.asyncio
async def test_check_budget_exceeded_cost(db):
    svc = BudgetService(db)
    await svc.update_limits("tenant1", max_cost_usd=1.0)
    await svc.record_usage("tenant1", cost_usd=0.8)
    result = await svc.check_budget("tenant1", estimated_cost=0.5)
    assert result["within_budget"] is False


@pytest.mark.asyncio
async def test_active_tasks(db):
    svc = BudgetService(db)
    budget = await svc.increment_active_tasks("tenant1")
    assert budget.active_tasks == 1
    budget = await svc.increment_active_tasks("tenant1")
    assert budget.active_tasks == 2
    budget = await svc.decrement_active_tasks("tenant1")
    assert budget.active_tasks == 1


@pytest.mark.asyncio
async def test_active_tasks_floor(db):
    svc = BudgetService(db)
    budget = await svc.decrement_active_tasks("tenant1")
    assert budget.active_tasks == 0


@pytest.mark.asyncio
async def test_usage_summary(db):
    svc = BudgetService(db)
    await svc.record_usage("tenant1", tokens=500, tool_calls=10, cost_usd=1.23, runtime_s=300)
    summary = await svc.get_usage_summary("tenant1")
    assert summary["tenant"] == "tenant1"
    assert summary["tokens"]["used"] == 500
    assert summary["tokens"]["limit"] == 1_000_000
    assert summary["tool_calls"]["used"] == 10


@pytest.mark.asyncio
async def test_usage_accumulates(db):
    svc = BudgetService(db)
    await svc.record_usage("tenant1", tokens=100, cost_usd=0.1)
    await svc.record_usage("tenant1", tokens=200, cost_usd=0.2)
    summary = await svc.get_usage_summary("tenant1")
    assert summary["tokens"]["used"] == 300
    assert abs(summary["cost_usd"]["used"] - 0.3) < 0.01
