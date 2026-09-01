"""Migration agent — Volume 67 Commit 2.

Migration runs reuse the deterministic change engine (refactor) so the
diff represents real textual changes. Rollback is an explicit, audible
operation over the created ``CodePatch``.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev import agent as agent_svc
from app.ai_dev import refactor as refactor_svc
from app.ai_dev.common import emit_event

logger = logging.getLogger(__name__)


async def run_migration(
    db: AsyncSession,
    tenant: str,
    run,
    *,
    user_id: Optional[str] = None,
) -> dict:
    return await refactor_svc.run_refactor(db, tenant, run, user_id=user_id)


async def rollback_migration(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    run_id,
    *,
    reason: Optional[str] = None,
) -> dict:
    from app.ai_dev import patch as patch_svc

    run = await agent_svc.get_agent_run(db, tenant, run_id)
    if run.agent_type != "migrate":
        raise ValueError(f"run {run_id} is not a migration agent")
    patch_id = (run.result or {}).get("patch_id")
    if not patch_id:
        raise ValueError("no applied patch to roll back")
    patch = await patch_svc.rollback_patch(db, tenant, user_id, patch_id)
    await emit_event(
        "CodeMigrationRolledBack",
        {
            "agent_run_id": str(run.id),
            "patch_id": str(patch.id),
            "reason": reason,
            "rolled_back_by": user_id,
        },
        tenant,
    )
    return {"agent_run_id": str(run.id), "patch_id": str(patch.id), "status": patch.status}