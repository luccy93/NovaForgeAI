"""Tests for patch creation, validation, scope detection."""

import pytest
from uuid import uuid4
from app.automation.task_service import TaskService
from app.automation.patch_service import PatchService
from app.automation.schemas import TaskCreate


@pytest.mark.asyncio
async def _create_task(db):
    svc = TaskService(db)
    return await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="fix", actor="u1",
    ))


@pytest.mark.asyncio
async def test_create_patch(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(
        task.id,
        diff="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new",
        file_changes=[{"path": "x.py", "action": "modify"}],
        added_lines=1, removed_lines=1, files_changed=1,
        reason="fix bug",
    )
    assert patch.task_id == task.id
    assert patch.status == "draft"
    assert patch.files_changed == 1


@pytest.mark.asyncio
async def test_validate_patch_success(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(task.id, diff="diff", reason="fix")
    patch = await svc.validate(patch.id, syntax_valid=True, imports_valid=True, security_clean=True)
    assert patch.status == "validated"


@pytest.mark.asyncio
async def test_validate_patch_rejected(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(task.id, diff="diff", reason="fix")
    patch = await svc.validate(patch.id, syntax_valid=False, errors=["syntax error"])
    assert patch.status == "rejected"
    assert "syntax error" in patch.validation_errors


@pytest.mark.asyncio
async def test_apply_patch(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(task.id, diff="diff", reason="fix")
    await svc.validate(patch.id, syntax_valid=True, imports_valid=True, security_clean=True)
    patch = await svc.apply(patch.id, commit_sha="abc123")
    assert patch.status == "applied"
    assert patch.commit_sha == "abc123"


@pytest.mark.asyncio
async def test_apply_unvalidated_patch_fails(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(task.id, diff="diff", reason="fix")
    with pytest.raises(ValueError, match="validated"):
        await svc.apply(patch.id)


@pytest.mark.asyncio
async def test_rollback_patch(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(task.id, diff="diff", reason="fix")
    await svc.validate(patch.id, syntax_valid=True, imports_valid=True, security_clean=True)
    await svc.apply(patch.id)
    patch = await svc.rollback(patch.id)
    assert patch.status == "rolled_back"


@pytest.mark.asyncio
async def test_scope_violation(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(
        task.id, diff="diff",
        file_changes=[{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}],
        reason="fix",
    )
    result = await svc.detect_scope_violation(patch.id, planned_files=["a.py", "b.py"])
    assert result["has_violation"] is True
    assert "c.py" in result["unexpected_files"]


@pytest.mark.asyncio
async def test_no_scope_violation(db):
    task = await _create_task(db)
    svc = PatchService(db)
    patch = await svc.create(
        task.id, diff="diff",
        file_changes=[{"path": "a.py"}, {"path": "b.py"}],
        reason="fix",
    )
    result = await svc.detect_scope_violation(patch.id, planned_files=["a.py", "b.py", "c.py"])
    assert result["has_violation"] is False


@pytest.mark.asyncio
async def test_list_patches(db):
    task = await _create_task(db)
    svc = PatchService(db)
    await svc.create(task.id, diff="d1", reason="r1")
    await svc.create(task.id, diff="d2", reason="r2")
    patches = await svc.list_for_task(task.id)
    assert len(patches) == 2
