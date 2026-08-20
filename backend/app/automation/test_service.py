"""Test generation, execution and failure-loop management."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationPatch, AutomationTestRun, TestResult

logger = logging.getLogger(__name__)


class TestService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_run(
        self,
        task_id: UUID,
        test_type: str,
        tests_total: int = 0,
        tests_passed: int = 0,
        tests_failed: int = 0,
        tests_skipped: int = 0,
        duration_ms: int = 0,
        output: str = "",
        failures: Optional[list] = None,
        patch_id: Optional[UUID] = None,
        iteration: int = 1,
    ) -> AutomationTestRun:
        if tests_failed > 0:
            result = TestResult.FAILED
        elif tests_total == 0:
            result = TestResult.ERROR
        else:
            result = TestResult.PASSED
        run = AutomationTestRun(
            task_id=task_id,
            patch_id=patch_id,
            test_type=test_type,
            tests_total=tests_total,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_skipped=tests_skipped,
            result=result,
            duration_ms=duration_ms,
            output=output,
            failures=failures or [],
            iteration=iteration,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def get(self, run_id: UUID) -> Optional[AutomationTestRun]:
        return await self.db.get(AutomationTestRun, run_id)

    async def list_for_task(self, task_id: UUID) -> list[AutomationTestRun]:
        res = await self.db.execute(
            select(AutomationTestRun)
            .where(AutomationTestRun.task_id == task_id)
            .order_by(AutomationTestRun.created_at.desc())
        )
        return list(res.scalars().all())

    async def latest_for_task(self, task_id: UUID) -> Optional[AutomationTestRun]:
        res = await self.db.execute(
            select(AutomationTestRun)
            .where(AutomationTestRun.task_id == task_id)
            .order_by(AutomationTestRun.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def should_retry(self, task_id: UUID, max_iterations: int = 5) -> bool:
        res = await self.db.execute(
            select(AutomationTestRun)
            .where(AutomationTestRun.task_id == task_id)
            .order_by(AutomationTestRun.iteration.desc())
            .limit(1)
        )
        latest = res.scalar_one_or_none()
        if not latest:
            return False
        if latest.result == TestResult.PASSED:
            return False
        if latest.iteration >= max_iterations:
            return False
        return True

    def select_tests(self, changed_files: list[str], all_test_files: list[str]) -> list[str]:
        affected = set()
        for f in changed_files:
            base = f.rsplit(".", 1)[0] if "." in f else f
            for tf in all_test_files:
                if base.split("/")[-1] in tf:
                    affected.add(tf)
        if not affected:
            affected = set(all_test_files)
        return sorted(affected)
