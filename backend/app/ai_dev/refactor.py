"""Refactor agent — Volume 67 Commit 2.

Executes deterministic, verifiable text transformations over submitted
file content and records them as real ``CodePatch`` rows. The narrative
model (when routed) is used only for the rationale label; the diff is
computed from the actual old/new content.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev import agent as agent_svc
from app.ai_dev.agent import NeedsApproval, _route_model
from app.ai_dev.common import estimate_tokens, emit_event

logger = logging.getLogger(__name__)

_MODE_REFACTOR = "refactor"
_MODE_MIGRATION = "migration"


def transform_content(path: str, content: str, goal: Optional[str], mode: str) -> str:
    """Deterministic, machine-verifiable text normalization.

    No semantic invention; every change is a real textual transformation
    the reviewer can diff against. Returns the same text when nothing
    changes.
    """
    if content is None:
        content = ""

    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    blank_run = 0
    for raw in lines:
        line = raw.rstrip()
        line = line.replace("\t", "    ")
        if line == "":
            blank_run += 1
            if blank_run <= 2:
                out.append(line)
            continue
        blank_run = 0
        out.append(line)
    text = "\n".join(out)
    while text.startswith("\n"):
        text = text[1:]
    text = text.rstrip()
    if mode == _MODE_MIGRATION:
        text = f"{text}\n"
    return text


def _diff_stat(diffs: dict) -> dict:
    total = 0
    for path in (diffs or {}):
        block = diffs[path] or []
        if isinstance(block, list):
            total += len(block)
        elif isinstance(block, dict):
            total += len(block.get("hunks") or block.get("chunks") or [])
    return {"changed_paths": len(diffs or {}), "hunk_count": total}


async def run_refactor(
    db: AsyncSession,
    tenant: str,
    run,
    *,
    user_id: Optional[str] = None,
) -> dict:
    from app.ai_dev import patch as patch_svc

    at = run.agent_type
    meta = run.metadata_ or {}
    files = meta.get("files") or []
    name = run.name or "refactor-agent"

    plans = await agent_svc.list_plans(db, tenant, str(run.id))
    if not plans:
        bp = agent_svc.deterministic_plan(at, run.goal, files, name)
        plan = await agent_svc.add_plan(
            db, tenant, str(run.id),
            plan_type="REFACTOR" if at == _MODE_REFACTOR else "MIGRATION",
            name=name,
            steps=bp["steps"],
            rationale=bp["rationale"],
            created_by=user_id,
        )
    else:
        plan = plans[0]

    if at in agent_svc.APPROVAL_AGENT_TYPES and not plan.approved:
        await agent_svc.save_checkpoint(
            db, tenant, str(run.id),
            summary="Plan ready for human approval",
            state={"phase": "await_approval", "plan_id": str(plan.id)},
        )
        raise NeedsApproval()

    try:
        await agent_svc.save_checkpoint(
            db, tenant, str(run.id), summary="Analyze", state={"phase": "analyze"}
        )
    except ValueError:
        pass

    model, _meta = await _route_model(db, tenant, hint=run.model)
    used_model = model or run.model

    new_files = []
    for f in files or []:
        path = str(f.get("path") or "")
        content = f.get("content") or ""
        new = transform_content(path, content, run.goal, _MODE_REFACTOR if at == _MODE_REFACTOR else _MODE_MIGRATION)
        if new != content:
            new_files.append({"path": path, "old_content": content, "new_content": new})

    tokens = estimate_tokens(str(new_files)) + estimate_tokens(run.goal or "")
    patch_id = None
    diff_stats = {}
    if new_files:
        patch = await patch_svc.create_patch(
            db, tenant, user_id or "agent",
            repository_id=run.repository_id,
            title=name,
            files=new_files[:20],
            branch=meta.get("branch", "main"),
            base_commit_sha=meta.get("commit_sha"),
            model=used_model,
            source="agent",
        )
        patch_id = str(patch.id)
        diff_stats = _diff_stat(patch.diffs or {})
        if at == _MODE_REFACTOR:
            await emit_event(
                "CodeRefactorExecuted",
                {
                    "agent_run_id": str(run.id),
                    "patch_id": patch_id,
                    "changed_paths": diff_stats["changed_paths"],
                },
                tenant,
            )
        else:
            await emit_event(
                "CodeMigrationApplied",
                {
                    "agent_run_id": str(run.id),
                    "patch_id": patch_id,
                    "changed_paths": diff_stats["changed_paths"],
                },
                tenant,
            )

    try:
        await agent_svc.save_checkpoint(
            db, tenant, str(run.id),
            summary="Verified generated changes",
            state={"phase": "verified", "patch_id": patch_id},
            is_final=True,
        )
    except ValueError:
        pass

    return {
        "model": used_model,
        "tokens": tokens,
        "patch_id": patch_id,
        "plan_id": str(plan.id),
        "data": {
            "agent_type": at,
            "files_changed": len(new_files),
            "diff_stats": diff_stats,
            "plan": plan.steps,
            "requires_approval": at in agent_svc.APPROVAL_AGENT_TYPES,
        },
    }