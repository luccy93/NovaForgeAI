"""Delivery Platform API — Endpoints (Volume 46)."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.delivery.pipeline_service import PipelineService
from app.delivery.runner_service import RunnerService
from app.delivery.artifact_service import ArtifactService
from app.delivery.environment_service import EnvironmentService
from app.delivery.deployment_service import DeploymentService
from app.delivery.release_service import ReleaseService
from app.delivery.preview_service import PreviewService
from app.delivery.approval_service import ApprovalService
from app.delivery.schemas import (
    PipelineCreate, PipelineResponse, PipelineRunCreate, PipelineRunResponse,
    JobResponse, RunnerCreate, RunnerResponse, ArtifactCreate, ArtifactResponse,
    EnvironmentCreate, EnvironmentResponse, DeploymentCreate, DeploymentResponse,
    ReleaseCreate, ReleaseResponse, RolloutResponse, RollbackCreate, RollbackResponse,
    PreviewEnvironmentCreate, PreviewEnvironmentResponse,
    ApprovalDecision, ApprovalResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/delivery", tags=["Software Delivery Platform"])


@router.post("/pipelines", response_model=PipelineResponse, status_code=201)
async def create_pipeline(data: PipelineCreate, db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    pipe = await svc.create(tenant=data.tenant, project=data.project, repository=data.repository,
                            branch=data.branch, name=data.name, trigger=data.trigger,
                            environment=data.environment, deployment_strategy=data.deployment_strategy,
                            timeout_s=data.timeout_s, variables=data.variables,
                            secrets_refs=data.secrets_refs)
    await db.commit()
    return pipe


@router.get("/pipelines", response_model=list[PipelineResponse])
async def list_pipelines(
    tenant: Optional[str] = None, project: Optional[str] = None,
    repository: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    svc = PipelineService(db)
    rows, _ = await svc.list_pipelines(tenant=tenant, project=project, repository=repository, limit=limit, offset=offset)
    return rows


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    pipe = await svc.get(pipeline_id)
    if not pipe:
        raise HTTPException(404, "pipeline not found")
    return pipe


@router.post("/pipelines/{pipeline_id}/run", response_model=PipelineRunResponse, status_code=201)
async def trigger_run(pipeline_id: UUID, data: PipelineRunCreate, db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    try:
        run = await svc.trigger_run(pipeline_id, commit_sha=data.commit_sha, trigger=data.trigger,
                                    actor=data.actor)
        await db.commit()
        return run
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/pipelines/{pipeline_id}/runs", response_model=list[PipelineRunResponse])
async def list_runs(pipeline_id: UUID, limit: int = 20, offset: int = 0,
                    db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    rows, _ = await svc.list_runs(pipeline_id, limit=limit, offset=offset)
    return rows


@router.get("/runs/{run_id}/jobs", response_model=list[JobResponse])
async def list_jobs(run_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    return await svc.get_jobs(run_id)


@router.post("/runners", response_model=RunnerResponse, status_code=201)
async def create_runner(data: RunnerCreate, db: AsyncSession = Depends(get_db)):
    svc = RunnerService(db)
    runner = await svc.register(**data.model_dump())
    await db.commit()
    return runner


@router.get("/runners", response_model=list[RunnerResponse])
async def list_runners(tenant: Optional[str] = None, region: Optional[str] = None,
                       status: Optional[str] = None, limit: int = 50, offset: int = 0,
                       db: AsyncSession = Depends(get_db)):
    svc = RunnerService(db)
    rows, _ = await svc.list_runners(tenant=tenant, region=region, status=status, limit=limit, offset=offset)
    return rows


@router.post("/runners/{runner_id}/heartbeat")
async def runner_heartbeat(runner_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = RunnerService(db)
    try:
        await svc.heartbeat(runner_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@router.post("/runners/{runner_id}/quarantine", response_model=RunnerResponse)
async def quarantine_runner(runner_id: UUID, reason: str = "", db: AsyncSession = Depends(get_db)):
    svc = RunnerService(db)
    try:
        runner = await svc.quarantine(runner_id, reason)
        await db.commit()
        return runner
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/artifacts", response_model=ArtifactResponse, status_code=201)
async def create_artifact(data: ArtifactCreate, db: AsyncSession = Depends(get_db)):
    svc = ArtifactService(db)
    d = data.model_dump()
    d["hash_val"] = d.pop("hash")
    artifact = await svc.create(**d)
    await db.commit()
    return artifact


@router.get("/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(tenant: Optional[str] = None, repository: Optional[str] = None,
                         artifact_type: Optional[str] = None, limit: int = 50, offset: int = 0,
                         db: AsyncSession = Depends(get_db)):
    svc = ArtifactService(db)
    rows, _ = await svc.list_artifacts(tenant=tenant, repository=repository,
                                       artifact_type=artifact_type, limit=limit, offset=offset)
    return rows


@router.get("/artifacts/{artifact_id}/verify")
async def verify_artifact(artifact_id: UUID, expected_hash: str,
                          db: AsyncSession = Depends(get_db)):
    svc = ArtifactService(db)
    return await svc.verify_integrity(artifact_id, expected_hash)


@router.post("/environments", response_model=EnvironmentResponse, status_code=201)
async def create_environment(data: EnvironmentCreate, db: AsyncSession = Depends(get_db)):
    svc = EnvironmentService(db)
    env = await svc.create(**data.model_dump())
    await db.commit()
    return env


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(tenant: Optional[str] = None, env_type: Optional[str] = None,
                            db: AsyncSession = Depends(get_db)):
    svc = EnvironmentService(db)
    return await svc.list_environments(tenant=tenant, env_type=env_type)


@router.post("/environments/{env_id}/lock", response_model=EnvironmentResponse)
async def lock_environment(env_id: UUID, locked_by: str = "operator",
                           db: AsyncSession = Depends(get_db)):
    svc = EnvironmentService(db)
    try:
        env = await svc.lock(env_id, locked_by)
        await db.commit()
        return env
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/environments/{env_id}/freeze", response_model=EnvironmentResponse)
async def freeze_environment(env_id: UUID, reason: str = "",
                             db: AsyncSession = Depends(get_db)):
    svc = EnvironmentService(db)
    try:
        env = await svc.freeze(env_id, reason)
        await db.commit()
        return env
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/environments/{env_id}/can-deploy")
async def can_deploy(env_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = EnvironmentService(db)
    return await svc.can_deploy(env_id)


@router.post("/deployments", response_model=DeploymentResponse, status_code=201)
async def create_deployment(data: DeploymentCreate, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.create(tenant="system", **data.model_dump())
        await db.commit()
        return dep
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/deployments", response_model=list[DeploymentResponse])
async def list_deployments(tenant: Optional[str] = None, environment_id: Optional[UUID] = None,
                           status: Optional[str] = None, limit: int = 20, offset: int = 0,
                           db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    rows, _ = await svc.list_deployments(tenant=tenant, environment_id=environment_id,
                                         status=status, limit=limit, offset=offset)
    return rows


@router.post("/deployments/{deployment_id}/start", response_model=DeploymentResponse)
async def start_deployment(deployment_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.start(deployment_id)
        await db.commit()
        return dep
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/deployments/{deployment_id}/complete", response_model=DeploymentResponse)
async def complete_deployment(deployment_id: UUID, health_status: str = "healthy",
                              db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.complete(deployment_id, health_status)
        await db.commit()
        return dep
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/deployments/{deployment_id}/approve", response_model=DeploymentResponse)
async def approve_deployment(deployment_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.approve(deployment_id, approved_by="operator")
        await db.commit()
        return dep
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/deployments/{deployment_id}/rollback", response_model=RollbackResponse)
async def rollback_deployment(deployment_id: UUID, data: RollbackCreate,
                              db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        rb = await svc.create_rollback(deployment_id, reason=data.reason,
                                       initiated_by=data.initiated_by,
                                       automatic=data.automatic)
        await db.commit()
        return rb
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/deployments/{deployment_id}/rollout", response_model=RolloutResponse)
async def create_rollout(deployment_id: UUID, strategy: str = "canary",
                         db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    rollout = await svc.create_rollout(deployment_id, strategy)
    await db.commit()
    return rollout


@router.post("/releases", response_model=ReleaseResponse, status_code=201)
async def create_release(data: ReleaseCreate, db: AsyncSession = Depends(get_db)):
    svc = ReleaseService(db)
    rel = await svc.create(**data.model_dump())
    await db.commit()
    return rel


@router.get("/releases", response_model=list[ReleaseResponse])
async def list_releases(tenant: Optional[str] = None, project: Optional[str] = None,
                        release_channel: Optional[str] = None, limit: int = 20, offset: int = 0,
                        db: AsyncSession = Depends(get_db)):
    svc = ReleaseService(db)
    rows, _ = await svc.list_releases(tenant=tenant, project=project,
                                      release_channel=release_channel, limit=limit, offset=offset)
    return rows


@router.post("/releases/{release_id}/promote", response_model=ReleaseResponse)
async def promote_release(release_id: UUID, environment: str,
                          db: AsyncSession = Depends(get_db)):
    svc = ReleaseService(db)
    try:
        rel = await svc.promote(release_id, environment)
        await db.commit()
        return rel
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/previews", response_model=PreviewEnvironmentResponse, status_code=201)
async def create_preview(data: PreviewEnvironmentCreate, db: AsyncSession = Depends(get_db)):
    svc = PreviewService(db)
    prev = await svc.create(**data.model_dump())
    await db.commit()
    return prev


@router.get("/previews", response_model=list[PreviewEnvironmentResponse])
async def list_previews(tenant: Optional[str] = None, repository: Optional[str] = None,
                        pr_number: Optional[int] = None,
                        db: AsyncSession = Depends(get_db)):
    svc = PreviewService(db)
    return await svc.list_previews(tenant=tenant, repository=repository, pr_number=pr_number)


@router.delete("/previews/{preview_id}", response_model=PreviewEnvironmentResponse)
async def destroy_preview(preview_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PreviewService(db)
    try:
        prev = await svc.destroy(preview_id)
        await db.commit()
        return prev
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/approvals", response_model=ApprovalResponse, status_code=201)
async def request_approval(requested_by: str = "operator", gate_type: str = "manual",
                           pipeline_run_id: Optional[UUID] = None,
                           deployment_id: Optional[UUID] = None,
                           db: AsyncSession = Depends(get_db)):
    svc = ApprovalService(db)
    approval = await svc.request(requested_by=requested_by, gate_type=gate_type,
                                 pipeline_run_id=pipeline_run_id, deployment_id=deployment_id)
    await db.commit()
    return approval


@router.get("/approvals", response_model=list[ApprovalResponse])
async def list_approvals(pipeline_run_id: Optional[UUID] = None,
                         deployment_id: Optional[UUID] = None,
                         decision: Optional[str] = None,
                         db: AsyncSession = Depends(get_db)):
    svc = ApprovalService(db)
    return await svc.list_approvals(pipeline_run_id=pipeline_run_id,
                                    deployment_id=deployment_id, decision=decision)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_decision(approval_id: UUID, data: ApprovalDecision,
                           db: AsyncSession = Depends(get_db)):
    svc = ApprovalService(db)
    try:
        approval = await svc.approve(approval_id, decided_by=data.decided_by, reason=data.reason)
        await db.commit()
        return approval
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_decision(approval_id: UUID, data: ApprovalDecision,
                          db: AsyncSession = Depends(get_db)):
    svc = ApprovalService(db)
    try:
        approval = await svc.reject(approval_id, decided_by=data.decided_by, reason=data.reason)
        await db.commit()
        return approval
    except ValueError as e:
        raise HTTPException(404, str(e))
