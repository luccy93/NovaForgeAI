"""Patch generation, validation and application tracking."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationPatch, PatchStatus

logger = logging.getLogger(__name__)


class PatchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        task_id: UUID,
        diff: str,
        file_changes: Optional[list] = None,
        added_lines: int = 0,
        removed_lines: int = 0,
        files_changed: int = 0,
        reason: str = "",
        plan_id: Optional[UUID] = None,
    ) -> AutomationPatch:
        patch = AutomationPatch(
            task_id=task_id,
            plan_id=plan_id,
            diff=diff,
            file_changes=file_changes or [],
            added_lines=added_lines,
            removed_lines=removed_lines,
            files_changed=files_changed,
            reason=reason,
            status=PatchStatus.DRAFT,
        )
        self.db.add(patch)
        await self.db.flush()
        return patch

    async def get(self, patch_id: UUID) -> Optional[AutomationPatch]:
        return await self.db.get(AutomationPatch, patch_id)

    async def list_for_task(self, task_id: UUID) -> list[AutomationPatch]:
        res = await self.db.execute(
            select(AutomationPatch)
            .where(AutomationPatch.task_id == task_id)
            .order_by(AutomationPatch.created_at.desc())
        )
        return list(res.scalars().all())

    async def validate(self, patch_id: UUID, syntax_valid: bool = False,
                       imports_valid: bool = False, security_clean: bool = False,
                       errors: Optional[list] = None) -> AutomationPatch:
        patch = await self.get(patch_id)
        if not patch:
            raise ValueError(f"patch {patch_id} not found")
        patch.syntax_valid = syntax_valid
        patch.imports_valid = imports_valid
        patch.security_clean = security_clean
        patch.validation_errors = errors or []
        if syntax_valid and imports_valid and security_clean:
            patch.status = PatchStatus.VALIDATED
        else:
            patch.status = PatchStatus.REJECTED
        await self.db.flush()
        return patch

    async def apply(self, patch_id: UUID, commit_sha: Optional[str] = None) -> AutomationPatch:
        patch = await self.get(patch_id)
        if not patch:
            raise ValueError(f"patch {patch_id} not found")
        if patch.status != PatchStatus.VALIDATED:
            raise ValueError(f"patch {patch_id} must be validated before applying (current: {patch.status})")
        patch.status = PatchStatus.APPLIED
        patch.commit_sha = commit_sha
        await self.db.flush()
        return patch

    async def rollback(self, patch_id: UUID) -> AutomationPatch:
        patch = await self.get(patch_id)
        if not patch:
            raise ValueError(f"patch {patch_id} not found")
        patch.status = PatchStatus.ROLLED_BACK
        await self.db.flush()
        return patch

    async def get_diff(self, patch_id: UUID) -> Optional[str]:
        patch = await self.get(patch_id)
        return patch.diff if patch else None

    async def detect_scope_violation(self, patch_id: UUID, planned_files: list[str]) -> dict:
        patch = await self.get(patch_id)
        if not patch:
            raise ValueError(f"patch {patch_id} not found")
        actual_files = [fc.get("path", "") for fc in patch.file_changes]
        unexpected = [f for f in actual_files if f not in planned_files]
        return {
            "has_violation": len(unexpected) > 0,
            "unexpected_files": unexpected,
            "planned_count": len(planned_files),
            "actual_count": len(actual_files),
        }
