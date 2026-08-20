"""Pipeline lifecycle: create, run, status, logs, cancel."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryPipeline, DeliveryPipelineRun, DeliveryJob

logger = logging.getLogger(__name__)

VALID_PIPELINE_STATES = ("queued", "running", "waiting_approval", "succeeded", "failed", "cancelled", "timed_out", "rolled_back")


class PipelineService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant: str, project: str, repository: str, branch: str,
                     name: str, trigger: str = "manual", stages: Optional[list] = None,
                     environment: str = "development", deployment_strategy: str = "rolling",
                     timeout_s: int = 3600, variables: Optional[dict] = None,
                     secrets_refs: Optional[list] = None, **kwargs) -> DeliveryPipeline:
        pipeline = DeliveryPipeline(
            tenant=tenant, project=project, repository=repository, branch=branch,
            name=name, trigger=trigger, stages=stages or [],
            environment=environment, deployment_strategy=deployment_strategy,
            timeout_s=timeout_s, variables=variables or {},
            secrets_refs=secrets_refs or [], **kwargs,
        )
        self.db.add(pipeline)
        await self.db.flush()
        return pipeline

    async def get(self, pipeline_id: UUID) -> Optional[DeliveryPipeline]:
        return await self.db.get(DeliveryPipeline, pipeline_id)

    async def list_pipelines(self, tenant: Optional[str] = None, project: Optional[str] = None,
                              repository: Optional[str] = None, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        stmt = select(DeliveryPipeline)
        count_stmt = select(func.count()).select_from(DeliveryPipeline)
        if tenant:
            stmt = stmt.where(DeliveryPipeline.tenant == tenant)
            count_stmt = count_stmt.where(DeliveryPipeline.tenant == tenant)
        if project:
            stmt = stmt.where(DeliveryPipeline.project == project)
            count_stmt = count_stmt.where(DeliveryPipeline.project == project)
        if repository:
            stmt = stmt.where(DeliveryPipeline.repository == repository)
            count_stmt = count_stmt.where(DeliveryPipeline.repository == repository)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(stmt.order_by(DeliveryPipeline.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return list(rows), total or 0

    async def trigger_run(self, pipeline_id: UUID, commit_sha: Optional[str] = None,
                           trigger: str = "manual", actor: str = "system",
                           context: Optional[dict] = None) -> DeliveryPipelineRun:
        pipeline = await self.get(pipeline_id)
        if not pipeline:
            raise ValueError(f"pipeline {pipeline_id} not found")
        run = DeliveryPipelineRun(
            pipeline_id=pipeline_id, commit_sha=commit_sha or "",
            trigger=trigger, status="queued", actor=actor,
            context=context or {},
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_run(self, run_id: UUID) -> Optional[DeliveryPipelineRun]:
        return await self.db.get(DeliveryPipelineRun, run_id)

    async def list_runs(self, pipeline_id: UUID, limit: int = 20, offset: int = 0) -> tuple[list, int]:
        stmt = select(DeliveryPipelineRun).where(DeliveryPipelineRun.pipeline_id == pipeline_id)
        count_stmt = select(func.count()).select_from(DeliveryPipelineRun).where(DeliveryPipelineRun.pipeline_id == pipeline_id)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(stmt.order_by(DeliveryPipelineRun.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return list(rows), total or 0

    async def start_run(self, run_id: UUID) -> DeliveryPipelineRun:
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"run {run_id} not found")
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await self.db.flush()
        return run

    async def complete_run(self, run_id: UUID, status: str = "succeeded", error: Optional[str] = None) -> DeliveryPipelineRun:
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"run {run_id} not found")
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        if run.started_at:
            run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        if error:
            run.error = error
        await self.db.flush()
        return run

    async def cancel_run(self, run_id: UUID) -> DeliveryPipelineRun:
        return await self.complete_run(run_id, status="cancelled")

    async def add_job(self, run_id: UUID, stage: str, name: str, image: str = "ubuntu:22.04",
                      commands: Optional[list] = None, environment_vars: Optional[dict] = None,
                      timeout_s: int = 600) -> DeliveryJob:
        job = DeliveryJob(
            pipeline_run_id=run_id, stage=stage, name=name,
            image=image, commands=commands or [],
            environment_vars=environment_vars or {}, timeout_s=timeout_s,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_jobs(self, run_id: UUID) -> list[DeliveryJob]:
        res = await self.db.execute(
            select(DeliveryJob).where(DeliveryJob.pipeline_run_id == run_id).order_by(DeliveryJob.created_at)
        )
        return list(res.scalars().all())

    async def get_job(self, job_id: UUID) -> Optional[DeliveryJob]:
        return await self.db.get(DeliveryJob, job_id)

    async def update_job_status(self, job_id: UUID, status: str, exit_code: Optional[int] = None,
                                 logs: Optional[str] = None) -> DeliveryJob:
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"job {job_id} not found")
        now = datetime.now(timezone.utc)
        if status == "running" and not job.started_at:
            job.started_at = now
        if status in ("succeeded", "failed", "cancelled"):
            job.finished_at = now
            if job.started_at:
                job.duration_ms = int((now - job.started_at).total_seconds() * 1000)
        job.status = status
        if exit_code is not None:
            job.exit_code = exit_code
        if logs is not None:
            job.logs = logs[:50000]
        await self.db.flush()
        return job
