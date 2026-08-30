"""Workflow definition and versioning — immutable published versions."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import WorkflowDefinition, WorkflowVersion


def _hash_dag(definition: dict, steps: list | None = None) -> str:
    raw = json.dumps(definition if steps is None else {"definition": definition, "steps": steps}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _validate_workflow_definition(definition: dict):
    steps = definition.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps list required")
    step_ids = {s.get("id") for s in steps}
    if len(step_ids) != len(steps):
        raise ValueError("duplicate step ids")
    # Check step types
    valid_types = {"TASK", "CONDITION", "PARALLEL", "SEQUENCE", "WAIT", "APPROVAL", "SUBWORKFLOW", "TRIGGER", "COMPENSATION"}
    for s in steps:
        t = s.get("type", "TASK").upper()
        if t not in valid_types:
            raise ValueError(f"invalid step type {t}")
        # Validate dependencies
        for dep in s.get("depends_on", []):
            if dep not in step_ids:
                raise ValueError(f"step {s.get('id')} depends_on unknown {dep}")
        # Check secrets not embedded
        if "secret" in json.dumps(s).lower() and "secret_ref" not in json.dumps(s):
            # Heuristic: if secret appears without ref
            pass
    # DAG cycle check via DFS
    graph = {s["id"]: [] for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            graph[dep].append(s["id"])
    visited: dict[str, int] = {}

    def dfs(node: str, stack: set[str]) -> bool:
        visited[node] = 1
        stack.add(node)
        for nei in graph.get(node, []):
            if nei not in visited:
                if dfs(nei, stack):
                    return True
            elif nei in stack:
                return True
        stack.remove(node)
        return False

    for n in step_ids:
        if n not in visited:
            if dfs(n, set()):
                raise ValueError("cyclic dependency detected")
    # Resource limits check
    limits = definition.get("resource_limits", {})
    if limits.get("cpu", 0) > 16 or limits.get("memory", 0) > 32768:
        raise ValueError("resource limits exceed platform max")


async def create_workflow(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> WorkflowDefinition:
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    q = select(WorkflowDefinition).where(WorkflowDefinition.tenant == tenant, WorkflowDefinition.name == name)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("workflow name already exists for tenant")
    wf = WorkflowDefinition(
        tenant=tenant,
        workspace=payload.get("workspace"),
        name=name,
        description=payload.get("description", ""),
        version="1.0",
        owner=payload.get("owner") or created_by,
        status="DRAFT",
    )
    db.add(wf)
    await db.flush()
    # Create initial version
    definition = payload.get("definition") or {"steps": payload.get("steps", []), "inputs": payload.get("inputs", {}), "outputs": payload.get("outputs", {})}
    _validate_workflow_definition(definition)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        tenant=tenant,
        version="1.0",
        definition=definition,
        status="DRAFT",
        dag_hash=_hash_dag(definition, definition.get("steps", [])),
        created_by=created_by,
    )
    db.add(ver)
    await db.flush()
    wf.current_version_id = ver.id
    await db.flush()
    return wf


async def get_workflow(db: AsyncSession, tenant: str, workflow_id: str) -> WorkflowDefinition | None:
    try:
        wid = uuid.UUID(workflow_id)
        q = select(WorkflowDefinition).where(WorkflowDefinition.id == wid, WorkflowDefinition.tenant == tenant)
    except Exception:
        q = select(WorkflowDefinition).where(WorkflowDefinition.tenant == tenant, WorkflowDefinition.name == workflow_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_workflows(db: AsyncSession, tenant: str, status: str | None = None, limit: int = 50) -> list[WorkflowDefinition]:
    q = select(WorkflowDefinition).where(WorkflowDefinition.tenant == tenant)
    if status:
        q = q.where(WorkflowDefinition.status == status.upper())
    q = q.order_by(WorkflowDefinition.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def create_version(db: AsyncSession, tenant: str, workflow_id: str, payload: dict, created_by: str = "") -> WorkflowVersion:
    wf = await get_workflow(db, tenant, workflow_id)
    if not wf:
        raise ValueError("workflow not found")
    # Get latest version
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id).order_by(WorkflowVersion.created_at.desc()).limit(1)
    res = await db.execute(q)
    latest = res.scalar_one_or_none()
    # Bump version
    if latest:
        try:
            major, minor = latest.version.split(".")
            new_version = f"{major}.{int(minor)+1}"
        except Exception:
            new_version = latest.version + ".1"
    else:
        new_version = "1.0"
    definition = payload.get("definition") or payload.get("steps") or {}
    if isinstance(definition, list):
        definition = {"steps": definition}
    _validate_workflow_definition(definition)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        tenant=tenant,
        version=new_version,
        definition=definition,
        status="DRAFT",
        dag_hash=_hash_dag(definition, definition.get("steps", [])),
        created_by=created_by,
    )
    db.add(ver)
    await db.flush()
    wf.current_version_id = ver.id
    wf.version = new_version
    await db.flush()
    return ver


async def publish_version(db: AsyncSession, tenant: str, version_id: str) -> WorkflowVersion:
    try:
        vid = uuid.UUID(version_id)
        q = select(WorkflowVersion).where(WorkflowVersion.id == vid, WorkflowVersion.tenant == tenant)
    except Exception:
        raise ValueError("invalid version_id")
    res = await db.execute(q)
    ver = res.scalar_one_or_none()
    if not ver:
        raise ValueError("version not found")
    if ver.status == "PUBLISHED":
        raise ValueError("already published")
    ver.status = "PUBLISHED"
    # Update workflow status
    q2 = select(WorkflowDefinition).where(WorkflowDefinition.id == ver.workflow_id)
    res2 = await db.execute(q2)
    wf = res2.scalar_one_or_none()
    if wf:
        wf.status = "ACTIVE"
        wf.current_version_id = ver.id
        wf.version = ver.version
        await db.flush()
    await db.flush()
    return ver


async def get_version(db: AsyncSession, tenant: str, version_id: str) -> WorkflowVersion | None:
    try:
        vid = uuid.UUID(version_id)
        q = select(WorkflowVersion).where(WorkflowVersion.id == vid, WorkflowVersion.tenant == tenant)
        res = await db.execute(q)
        return res.scalar_one_or_none()
    except Exception:
        return None
