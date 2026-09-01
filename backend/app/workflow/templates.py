"""Workflow templates — versioned, immutable, governed."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, Text, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class WorkflowTemplate(Base, TimestampMixin):
    __tablename__ = "workflow_templates"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general")  # CI/CD, security, data, incident, backup, AI
    definition: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "name", "version", name="uq_workflow_templates_tenant_name_version"),
        Index("ix_templates_tenant_category", "tenant", "category"),
    )


TEMPLATES = {
    "ci_cd": {"name": "CI/CD Pipeline", "steps": [{"id": "build", "type": "TASK"}, {"id": "test", "type": "TASK", "depends_on": ["build"]}, {"id": "deploy", "type": "TASK", "depends_on": ["test"]}]},
    "security_response": {"name": "Security Response", "steps": [{"id": "contain", "type": "TASK"}, {"id": "investigate", "type": "TASK", "depends_on": ["contain"]}]},
    "data_pipeline": {"name": "Data Pipeline", "steps": [{"id": "ingest", "type": "TASK"}, {"id": "transform", "type": "TASK", "depends_on": ["ingest"]}]},
    "incident_response": {"name": "Incident Response", "steps": [{"id": "detect", "type": "TASK"}, {"id": "triage", "type": "APPROVAL", "depends_on": ["detect"]}]},
    "backup_recovery": {"name": "Backup Recovery", "steps": [{"id": "backup", "type": "TASK"}, {"id": "verify", "type": "TASK", "depends_on": ["backup"]}]},
    "ai_evaluation": {"name": "AI Evaluation", "steps": [{"id": "evaluate", "type": "TASK"}]},
}


async def list_templates(db: AsyncSession, tenant: str) -> list[WorkflowTemplate]:
    # Return built-in + DB
    built_in = [{"name": k, "version": "1.0", "category": k, "is_published": True, "owner": "system"} for k in TEMPLATES]
    q = select(WorkflowTemplate).where(WorkflowTemplate.tenant == tenant)
    res = await db.execute(q)
    db_templates = res.scalars().all()
    # Merge
    return built_in + [{"name": t.name, "version": t.version, "category": t.category, "is_published": t.is_published, "owner": t.owner} for t in db_templates]


async def create_template(db: AsyncSession, tenant: str, payload: dict, owner: str) -> WorkflowTemplate:
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    # Check unsafe: no arbitrary shell, unbounded loops, credential extraction
    definition = payload.get("definition", {})
    steps = definition.get("steps", payload.get("steps", []))
    for s in steps:
        action = str(s.get("action") or "").lower()
        if s.get("action") and ("rm -rf" in action or "shell" in action or "eval" in action or "exec(" in str(s.get("action"))):
            raise ValueError("unsafe shell execution not allowed")
        if s.get("type") == "PARALLEL" and s.get("fan_out", 0) > 100:
            raise ValueError("unbounded fan-out")
        loop = s.get("loop", {})
        if isinstance(loop, dict) and loop.get("max_iterations", 0) > 1000:
            raise ValueError("unbounded loop")
    tmpl = WorkflowTemplate(
        tenant=tenant,
        name=name,
        description=payload.get("description", ""),
        category=payload.get("category", "general"),
        definition=definition,
        version=payload.get("version", "1.0"),
        owner=owner,
        is_published=False,
    )
    db.add(tmpl)
    await db.flush()
    return tmpl


async def publish_template(db: AsyncSession, tenant: str, template_id: str, approver: str) -> WorkflowTemplate:
    try:
        tid = uuid.UUID(template_id)
        q = select(WorkflowTemplate).where(WorkflowTemplate.id == tid, WorkflowTemplate.tenant == tenant)
        res = await db.execute(q)
        tmpl = res.scalar_one_or_none()
    except Exception:
        raise ValueError("template not found")
    if not tmpl:
        raise ValueError("template not found")
    if tmpl.is_published:
        raise ValueError("already published")
    # Requires approval
    if not approver:
        raise ValueError("approver required")
    tmpl.is_published = True
    tmpl.approved_by = approver
    await db.flush()
    return tmpl
