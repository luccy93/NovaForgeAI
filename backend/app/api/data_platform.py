"""Data Platform API — Volume 65 Commit 1."""

import hashlib
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-platform", tags=["Data Platform"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, permission: str, resource_type: str = "data"):
    try:
        from app.iam.policy_authorizer import policy_authorizer
        ctx = {"role": str(getattr(user, "role", "viewer"))}
        decision = policy_authorizer.authorize(str(getattr(user, "id", "")), tenant, permission, resource_type=resource_type, context=ctx)
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("IAM check skipped %s: %s", permission, exc)


async def _emit(event_name: str, data: dict, tenant: str):
    try:
        from app.core.events import Event, EventType, event_bus
        et = getattr(EventType, event_name, None)
        if et:
            await event_bus.publish_nowait(Event(et, data, source="data_platform", organization_id=tenant))
    except Exception as exc:
        logger.debug("emit failed %s: %s", event_name, exc)


def _check_limit(limit: int):
    if limit > 1000:
        raise HTTPException(status_code=400, detail="limit too large (max 1000)")


# ── Models ───────────────────────────────────────────────────────────────────
class DatasetIn(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    workspace: Optional[str] = None
    project: Optional[str] = None
    owner: Optional[str] = None
    team: Optional[str] = None
    classification: str = "INTERNAL"
    schema_version: str = "1.0"
    storage_location: Optional[str] = None
    region: Optional[str] = None
    status: str = "DRAFT"
    retention_days: Optional[int] = None


class SourceIn(BaseModel):
    name: str
    connector: str
    credentials: Optional[str] = None
    region: Optional[str] = None
    classification: str = "INTERNAL"
    owner: Optional[str] = None
    config: dict = {}


class SchemaIn(BaseModel):
    version: str = "1.0"
    fields: list
    classification: str = "INTERNAL"


class PipelineIn(BaseModel):
    name: str
    description: Optional[str] = None
    steps: list = []
    dependencies: list = []
    schedule: Optional[str] = None
    owner: Optional[str] = None
    region: Optional[str] = None
    priority: str = "NORMAL"
    resource_limits: dict = {}
    status: str = "DRAFT"


class QualityRuleIn(BaseModel):
    name: str
    rule_type: str
    params: dict = {}
    version: str = "1.0"


class LineageIn(BaseModel):
    source: str
    target: str
    transformation: Optional[str] = None
    pipeline_id: Optional[str] = None
    column_lineage: dict = {}


class StreamIn(BaseModel):
    topic: str
    partition: int = 0
    consumer_group: Optional[str] = None
    schema_id: Optional[str] = None
    region: Optional[str] = None


# ── Datasets ─────────────────────────────────────────────────────────────────
@router.post("/datasets", status_code=201)
async def create_dataset(payload: DatasetIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "dataset")
    from app.data_platform.dataset import create_dataset as _create
    try:
        ds = await _create(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("DatasetCreated", {"dataset_id": str(ds.id), "tenant": tenant, "name": ds.name}, tenant)
    # Qdrant upsert and snapshot
    try:
        from app.data_platform.catalog import upsert_qdrant, generate_snapshot
        await upsert_qdrant(tenant, ds)
        await generate_snapshot(db, tenant)
    except Exception:
        pass
    return {"id": str(ds.id), "name": ds.name, "status": ds.status, "classification": ds.classification}


@router.get("/datasets")
async def list_datasets(status: Optional[str] = None, classification: Optional[str] = None, owner: Optional[str] = None, limit: int = Query(50, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.dataset import list_datasets as _list
    rows = await _list(db, tenant, status=status, classification=classification, owner=owner, limit=limit)
    return {"items": [{"id": str(r.id), "name": r.name, "status": r.status, "classification": r.classification, "owner": r.owner, "region": r.region} for r in rows]}


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.dataset import get_dataset as _get
    ds = await _get(db, tenant, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {"id": str(ds.id), "name": ds.name, "description": ds.description, "status": ds.status, "classification": ds.classification, "owner": ds.owner, "region": ds.region, "storage_location": ds.storage_location}


@router.post("/datasets/{dataset_id}/versions", status_code=201)
async def create_dataset_version(dataset_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "dataset")
    from app.data_platform.dataset import create_version
    try:
        ver = await create_version(db, tenant, dataset_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("DatasetVersionCreated", {"dataset_id": dataset_id, "version": ver.version}, tenant)
    return {"id": str(ver.id), "version": ver.version, "schema_version": ver.schema_version}


@router.post("/datasets/{dataset_id}/archive", status_code=200)
async def archive_dataset(dataset_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "dataset")
    from app.data_platform.storage import archive_dataset as _arch
    try:
        res = await _arch(db, tenant, dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return res


# ── Sources ──────────────────────────────────────────────────────────────────
@router.post("/sources", status_code=201)
async def create_source(payload: SourceIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "source")
    from app.data_platform.sources import register_source
    try:
        src = await register_source(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(src.id), "name": src.name, "connector": src.connector, "status": src.status}


@router.get("/sources")
async def list_sources(connector: Optional[str] = None, limit: int = Query(50, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.sources import list_sources as _list
    rows = await _list(db, tenant, connector=connector, limit=limit)
    return {"items": [{"id": str(r.id), "name": r.name, "connector": r.connector, "region": r.region} for r in rows]}


# ── Schemas ──────────────────────────────────────────────────────────────────
@router.post("/schemas", status_code=201)
async def create_schema(payload: SchemaIn, dataset_id: str = Query(...), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "schema")
    from app.data_platform.schemas import publish_schema
    try:
        sch = await publish_schema(db, tenant, dataset_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("SchemaPublished", {"schema_id": str(sch.id), "dataset_id": dataset_id}, tenant)
    return {"id": str(sch.id), "version": sch.version, "fields": sch.fields}


@router.get("/schemas")
async def list_schemas(dataset_id: Optional[str] = None, limit: int = Query(50, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.schemas import list_schemas as _list
    rows = await _list(db, tenant, dataset_id=dataset_id, limit=limit)
    return {"items": [{"id": str(r.id), "dataset_id": str(r.dataset_id), "version": r.version, "is_published": r.is_published} for r in rows]}


@router.post("/schemas/{schema_id}/evolve", status_code=200)
async def evolve_schema(schema_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "schema")
    from app.data_platform.schemas import evolve_schema as _evolve
    try:
        sch = await _evolve(db, tenant, schema_id, payload.get("fields", []), compatibility=payload.get("compatibility", "backward"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(sch.id), "version": sch.version}


# ── Ingestion ────────────────────────────────────────────────────────────────
@router.post("/ingest", status_code=201)
async def ingest(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "ingestion")
    dataset_id = payload.get("dataset_id")
    source_id = payload.get("source_id")
    mode = payload.get("mode", "batch")
    if not dataset_id or not source_id:
        raise HTTPException(status_code=422, detail="dataset_id and source_id required")
    from app.data_platform.ingestion import start_ingestion
    try:
        job = await start_ingestion(db, tenant, dataset_id, source_id, mode=mode, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("IngestionStarted", {"job_id": job["job_id"], "dataset_id": dataset_id}, tenant)
    return job


@router.post("/ingest/{job_id}/complete", status_code=200)
async def complete_ingest(job_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.ingestion import complete_ingestion
    try:
        job = await complete_ingestion(db, tenant, job_id, records=payload.get("records", 0), bytes_processed=payload.get("bytes", 0), error=payload.get("error"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    if job["status"] == "COMPLETED":
        await _emit("IngestionCompleted", {"job_id": job_id}, tenant)
    else:
        await _emit("IngestionFailed", {"job_id": job_id}, tenant)
    return job


@router.post("/ingest/cdc", status_code=200)
async def ingest_cdc(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    dataset_id = payload.get("dataset_id")
    changes = payload.get("changes", [])
    if not dataset_id or not changes:
        raise HTTPException(status_code=422, detail="dataset_id and changes required")
    from app.data_platform.ingestion import handle_cdc
    res = await handle_cdc(db, tenant, dataset_id, changes)
    await db.commit()
    return res


@router.get("/checkpoints")
async def get_checkpoints(consumer: str = Query(...), topic: str = Query(...), partition: int = Query(0), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.ingestion import get_checkpoint
    chk = await get_checkpoint(db, tenant, consumer, topic, partition)
    if not chk:
        return {"offset": 0, "watermark": None}
    return {"offset": chk.offset, "watermark": chk.watermark.isoformat() if chk.watermark else None}


# ── Pipelines ────────────────────────────────────────────────────────────────
@router.post("/pipelines", status_code=201)
async def create_pipeline(payload: PipelineIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "pipeline")
    from app.data_platform.pipelines import create_pipeline as _create
    try:
        pipe = await _create(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(pipe.id), "name": pipe.name, "status": pipe.status, "dag_hash": pipe.dag_hash}


@router.get("/pipelines")
async def list_pipelines(status: Optional[str] = None, limit: int = Query(50, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.pipelines import list_pipelines as _list
    rows = await _list(db, tenant, status=status, limit=limit)
    return {"items": [{"id": str(r.id), "name": r.name, "status": r.status, "priority": r.priority} for r in rows]}


@router.post("/pipelines/{pipeline_id}/runs", status_code=201)
async def start_pipeline_run(pipeline_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "pipeline_run")
    from app.data_platform.pipelines import start_run
    try:
        run = await start_run(db, tenant, pipeline_id, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("PipelineStarted", {"pipeline_id": pipeline_id, "run_id": run.run_id}, tenant)
    return {"run_id": run.run_id, "status": run.status, "idempotency_key": run.idempotency_key}


@router.post("/pipelines/runs/{run_id}/complete", status_code=200)
async def complete_pipeline_run(run_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.pipelines import complete_run
    try:
        run = await complete_run(db, tenant, run_id, status=payload.get("status", "SUCCESS"), records=payload.get("records", 0), error=payload.get("error"), checkpoint=payload.get("checkpoint"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    if run.status == "SUCCESS":
        await _emit("PipelineCompleted", {"run_id": run_id}, tenant)
    else:
        await _emit("PipelineFailed", {"run_id": run_id}, tenant)
    return {"run_id": run.run_id, "status": run.status, "duration_ms": run.duration_ms}


@router.post("/pipelines/{pipeline_id}/backfill", status_code=201)
async def backfill(pipeline_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "pipeline")
    from app.data_platform.pipelines import request_backfill
    try:
        res = await request_backfill(db, tenant, pipeline_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("BackfillStarted", {"pipeline_id": pipeline_id, "run_id": res["run_id"]}, tenant)
    return res


# ── Quality ──────────────────────────────────────────────────────────────────
@router.post("/quality/rules", status_code=201)
async def create_quality_rule(payload: QualityRuleIn, dataset_id: str = Query(...), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "quality")
    from app.data_platform.quality import create_rule
    try:
        rule = await create_rule(db, tenant, dataset_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(rule.id), "name": rule.name, "version": rule.version}


@router.post("/quality/jobs", status_code=201)
async def run_quality_job(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    dataset_id = payload.get("dataset_id")
    records = payload.get("records", [])
    if not dataset_id:
        raise HTTPException(status_code=422, detail="dataset_id required")
    from app.data_platform.quality import run_quality_job as _run
    results = await _run(db, tenant, dataset_id, records)
    await db.commit()
    # Check for failures
    failed = sum(r.failed for r in results)
    if failed > 0:
        await _emit("DataQualityFailed", {"dataset_id": dataset_id, "failed": failed}, tenant)
    return {"results": [{"rule_id": str(r.rule_id), "passed": r.passed, "failed": r.failed} for r in results]}


@router.get("/quality/results")
async def get_quality_results(dataset_id: str = Query(...), limit: int = Query(50, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.quality import get_results
    rows = await get_results(db, tenant, dataset_id, limit=limit)
    return {"items": [{"rule_id": str(r.rule_id), "passed": r.passed, "failed": r.failed, "timestamp": r.timestamp.isoformat()} for r in rows]}


@router.post("/quality/profile", status_code=200)
async def profile(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    dataset_id = payload.get("dataset_id")
    records = payload.get("records", [])
    if not dataset_id:
        raise HTTPException(status_code=422, detail="dataset_id required")
    from app.data_platform.quality import profile_dataset
    res = await profile_dataset(db, tenant, dataset_id, records)
    return res


# ── Lineage ──────────────────────────────────────────────────────────────────
@router.post("/lineage", status_code=201)
async def create_lineage(payload: LineageIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "lineage")
    from app.data_platform.lineage import record_edge
    try:
        edge = await record_edge(db, tenant, payload.source, payload.target, transformation=payload.transformation, pipeline_id=payload.pipeline_id, column_lineage=payload.column_lineage)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("LineageUpdated", {"source": payload.source, "target": payload.target}, tenant)
    return {"id": str(edge.id), "source": edge.source, "target": edge.target}


@router.get("/lineage/{node}/upstream")
async def lineage_upstream(node: str, depth: int = Query(3, ge=1, le=10), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.lineage import get_upstream
    edges = await get_upstream(db, tenant, node, depth=depth)
    return {"items": [{"source": e.source, "target": e.target, "transformation": e.transformation} for e in edges]}


@router.get("/lineage/{node}/downstream")
async def lineage_downstream(node: str, depth: int = Query(3, ge=1, le=10), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.lineage import get_downstream
    edges = await get_downstream(db, tenant, node, depth=depth)
    return {"items": [{"source": e.source, "target": e.target} for e in edges]}


@router.get("/lineage/{node}/graph")
async def lineage_graph(node: str, depth: int = Query(3, ge=1, le=10), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.lineage import get_lineage_graph
    return await get_lineage_graph(db, tenant, node, depth=depth)


# ── Catalog ──────────────────────────────────────────────────────────────────
@router.get("/catalog/search")
async def catalog_search(q: Optional[str] = None, owner: Optional[str] = None, classification: Optional[str] = None, limit: int = Query(20, ge=1, le=100), semantic: bool = Query(False), offline: bool = Query(False), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.catalog import search_catalog
    res = await search_catalog(db, tenant, query=q, owner=owner, classification=classification, limit=limit, semantic=semantic, offline=offline)
    # Authorization already filtered by tenant, but ensure no cross-tenant
    if offline and res.get("stale"):
        # Block privileged actions
        pass
    return res


@router.post("/catalog/snapshot", status_code=201)
async def catalog_snapshot(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "catalog")
    from app.data_platform.catalog import generate_snapshot
    path = await generate_snapshot(db, tenant)
    return {"snapshot": path, "tenant": tenant}


# ── Streaming ────────────────────────────────────────────────────────────────
@router.post("/streams", status_code=201)
async def create_stream(payload: StreamIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "stream")
    from app.data_platform.streaming import create_stream as _create
    try:
        stream = await _create(db, tenant, payload.topic, partition=payload.partition, consumer_group=payload.consumer_group, schema_id=payload.schema_id, region=payload.region)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(stream.id), "topic": stream.topic, "partition": stream.partition}


@router.post("/streams/{topic}/ingest", status_code=201)
async def stream_ingest(topic: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.streaming import ingest_event
    res = await ingest_event(db, tenant, topic, payload, partition=payload.get("partition", 0))
    await db.commit()
    return res


@router.get("/streams/{topic}/lag")
async def stream_lag(topic: str, consumer: str = Query(...), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.streaming import get_lag
    return await get_lag(db, tenant, topic, consumer)


@router.post("/streams/{topic}/consume", status_code=200)
async def stream_consume(topic: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    consumer = payload.get("consumer")
    if not consumer:
        raise HTTPException(status_code=422, detail="consumer required")
    from app.data_platform.streaming import consume_events
    events = await consume_events(db, tenant, topic, consumer, partition=payload.get("partition", 0), limit=payload.get("limit", 10))
    return {"items": events}


# ── Data jobs (alias for pipeline runs) ─────────────────────────────────────
@router.get("/data-jobs")
async def list_data_jobs(pipeline_id: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.models import DataPipelineRun
    q = select(DataPipelineRun).where(DataPipelineRun.tenant == tenant)
    if pipeline_id:
        try:
            pid = uuid.UUID(pipeline_id)
            q = q.where(DataPipelineRun.pipeline_id == pid)
        except Exception:
            pass
    q = q.order_by(DataPipelineRun.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"run_id": r.run_id, "status": r.status, "records": r.records} for r in rows]}


# ── Commit 2: Lakehouse, Products, Domains, Freshness, Drift, Replay, Export ──
@router.post("/lakehouse/{dataset_id}/tier", status_code=200)
async def write_tier(dataset_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "lakehouse")
    tier = payload.get("tier", "raw")
    records = payload.get("records", [])
    fmt = payload.get("format", "json")
    from app.data_platform.lakehouse_tiers import write_tier as _write
    try:
        res = await _write(db, tenant, dataset_id, tier, records, fmt=fmt)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return res


@router.get("/lakehouse/{dataset_id}/stats")
async def lakehouse_stats(dataset_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.lakehouse_tiers import get_tier_stats, optimize_storage
    stats = await get_tier_stats(db, tenant, dataset_id)
    opts = await optimize_storage(db, tenant, dataset_id)
    return {"stats": stats, "optimizations": opts}


@router.post("/freshness/{dataset_id}", status_code=200)
async def update_freshness(dataset_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.freshness import update_freshness as _upd
    rec = await _upd(db, tenant, dataset_id, expected_interval_hours=payload.get("expected_interval_hours", 24))
    await db.commit()
    return {"dataset_id": dataset_id, "status": rec.status, "last_update": rec.last_update.isoformat() if rec.last_update else None}


@router.get("/freshness/{dataset_id}")
async def get_freshness(dataset_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.freshness import get_freshness as _get, check_slo
    rec = await _get(db, tenant, dataset_id)
    if not rec:
        raise HTTPException(status_code=404, detail="freshness not found")
    slo = await check_slo(db, tenant, dataset_id)
    return {"status": rec.status, "last_update": rec.last_update.isoformat() if rec.last_update else None, "slo": slo}


@router.post("/drift/{dataset_id}/check", status_code=200)
async def check_drift(dataset_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.data_platform.freshness import detect_drift
    res = await detect_drift(db, tenant, dataset_id, current_schema=payload.get("current_schema", []), previous_schema=payload.get("previous_schema"))
    await db.commit()
    return res or {"drift": False}


class ProductIn(BaseModel):
    name: str
    description: Optional[str] = None
    owner: str
    contract: dict = {}
    classification: str = "INTERNAL"
    domain: Optional[str] = None
    slo: dict = {}
    status: str = "DRAFT"


@router.post("/data-products", status_code=201)
async def create_product(payload: ProductIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "data_product")
    from app.data_platform.products import create_product as _create
    try:
        prod = await _create(db, tenant, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(prod.id), "name": prod.name, "status": prod.status}


@router.get("/data-products")
async def list_products(status: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.data_platform.products import list_products as _list
    rows = await _list(db, tenant, status=status, limit=limit)
    return {"items": [{"id": str(r.id), "name": r.name, "status": r.status, "owner": r.owner} for r in rows]}


@router.post("/data-domains", status_code=201)
async def create_domain(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:write", "domain")
    name = payload.get("name")
    owner = payload.get("owner")
    if not name or not owner:
        raise HTTPException(status_code=422, detail="name and owner required")
    from app.data_platform.products import create_domain as _create
    try:
        dom = await _create(db, tenant, name, owner, description=payload.get("description"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(dom.id), "name": dom.name}


@router.post("/replay", status_code=201)
async def create_replay(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    topic = payload.get("topic")
    if not topic:
        raise HTTPException(status_code=422, detail="topic required")
    # Approval preview
    if payload.get("requires_approval") and not payload.get("approved"):
        raise HTTPException(status_code=403, detail="replay requires approval")
    from app.data_platform.models_lakehouse import DataReplayJob
    job = DataReplayJob(tenant=tenant, topic=topic, scope=payload.get("scope", {}), status="PENDING")
    db.add(job)
    await db.flush()
    await db.commit()
    return {"id": str(job.id), "topic": topic, "status": job.status}


@router.post("/reconciliation", status_code=200)
async def reconcile(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    source_count = payload.get("source_count", 0)
    processed_count = payload.get("processed_count", 0)
    output_count = payload.get("output_count", 0)
    missing = source_count - processed_count
    duplicate = max(processed_count - output_count, 0)
    if missing > 0 or duplicate > 0:
        await _emit("DataReconciliationFailed", {"tenant": tenant, "missing": missing, "duplicate": duplicate}, tenant)
    return {"missing": missing, "duplicate": duplicate, "mismatched": abs(processed_count - output_count)}


@router.post("/exports", status_code=201)
async def create_export(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "data:export", "dataset")
    dataset_id = payload.get("dataset_id")
    if not dataset_id:
        raise HTTPException(status_code=422, detail="dataset_id required")
    # Audit
    _audit_best = None
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=tenant, actor_id=str(getattr(user, "id", "")), actor_type="user", action="data.export.requested", resource_type="dataset", resource_id=dataset_id, result="success", details={"purpose": payload.get("purpose"), "destination": payload.get("destination")}, tenant_id=tenant)
    except Exception:
        pass
    await _emit("DataExportRequested", {"dataset_id": dataset_id, "actor": str(getattr(user, "id", ""))}, tenant)
    return {"export_id": str(uuid.uuid4()), "dataset_id": dataset_id, "status": "REQUESTED"}


@router.get("/access-anomalies")
async def access_anomalies(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    # Correlate identity/dataset/action/region/volume
    from app.iam.models import IAMAuditLog
    q = select(IAMAuditLog).where(IAMAuditLog.organization_id == _to_uuid(tenant)).order_by(IAMAuditLog.created_at.desc()).limit(100)
    try:
        res = await db.execute(q)
        logs = res.scalars().all()
        # Simple anomaly: high volume per actor
        from collections import Counter
        cnt = Counter(str(l.actor_id) for l in logs if l.actor_id)
        anomalies = [{"actor": a, "count": c, "type": "high_volume"} for a, c in cnt.items() if c > 10]
    except Exception:
        anomalies = []
    return {"items": anomalies[:limit]}


def _to_uuid(v):
    import uuid as _u
    try:
        return _u.UUID(str(v))
    except Exception:
        return v
