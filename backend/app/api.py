"""NovaForge Unified API — REST gateway for all 30 volumes."""
import logging, json
from typing import Optional
from datetime import datetime, timezone

try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi import UploadFile, File
    from fastapi import Request
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    BaseModel = object

from app.common.services import registry

logger = logging.getLogger(__name__)

if HAS_FASTAPI:
    router = APIRouter(prefix="/api/v1", tags=["NovaForge"])

    # ─── Models ───
    class HealthResponse(BaseModel):
        status: str; volumes: int; timestamp: str

    class TelemetryResponse(BaseModel):
        total_operations: int; per_volume: dict

    # ─── Global Endpoints ───
    @router.get("/health", response_model=HealthResponse)
    async def health():
        checks = registry.health_check()
        return HealthResponse(
            status="healthy" if all(v.get("status") == "healthy" for v in checks.values()) else "degraded",
            volumes=len(checks),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @router.get("/telemetry", response_model=TelemetryResponse)
    async def telemetry():
        snap = registry.telemetry_snapshot()
        return TelemetryResponse(
            total_operations=sum(sum(v.values()) for v in snap.values()),
            per_volume=snap,
        )

    @router.get("/volumes")
    async def list_volumes():
        return {"volumes": sorted(registry._services.keys()), "count": len(registry._services)}

    # ─── Volume Health Endpoints ───
    @router.get("/health/{volume}")
    async def volume_health(volume: str):
        checks = registry.health_check()
        if volume not in checks:
            raise HTTPException(404, f"Volume '{volume}' not found")
        return checks[volume]

    # ─── Release Engineering (Volume 24) ───
    @router.post("/releases")
    async def create_release(org_id: str = Query(...), name: str = Query(...), version: str = Query(...), channel: str = "stable"):
        svc = registry.get("release_engineering")
        if not svc: raise HTTPException(404, "Release Engineering not available")
        return await svc.create_release(org_id, name, version, channel)

    @router.post("/deployments")
    async def deploy(org_id: str = Query(...), release_id: str = Query(...), environment: str = Query(...), strategy: str = "rolling"):
        svc = registry.get("release_engineering")
        if not svc: raise HTTPException(404, "Release Engineering not available")
        return await svc.deploy(org_id, release_id, environment, strategy)

    # ─── Real-Time Collaboration (Volume 25) ───
    @router.post("/rtc/messages")
    async def send_message(org_id: str = Query(...), channel_id: str = Query(...), sender_id: str = Query(...), content: str = Query(...)):
        svc = registry.get("realtime_collaboration")
        if not svc: raise HTTPException(404, "RTC not available")
        return await svc.send_message(org_id, channel_id, sender_id, content)

    @router.post("/rtc/meetings")
    async def start_meeting(org_id: str = Query(...), title: str = Query(...), organizer_id: str = ""):
        svc = registry.get("realtime_collaboration")
        if not svc: raise HTTPException(404, "RTC not available")
        return await svc.start_meeting(org_id, title, organizer_id)

    # ─── AIOps (Volume 26) ───
    @router.post("/aiops/heal")
    async def auto_heal(org_id: str = Query(...), incident_type: str = Query(...), message: str = Query(...), severity: str = "medium"):
        svc = registry.get("aiops")
        if not svc: raise HTTPException(404, "AIOps not available")
        return await svc.detect_and_heal(org_id, incident_type, message, severity)

    @router.post("/aiops/chaos")
    async def run_chaos(org_id: str = Query(...), name: str = Query(...), exp_type: str = Query(...), target: str = ""):
        svc = registry.get("aiops")
        if not svc: raise HTTPException(404, "AIOps not available")
        return await svc.run_chaos_test(org_id, name, exp_type, target)

    # ─── Security (Volume 27) ───
    @router.post("/security/scan")
    async def scan_repo(org_id: str = Query(...), repo_id: str = Query(...), scan_type: str = "full"):
        svc = registry.get("security_compliance")
        if not svc: raise HTTPException(404, "Security not available")
        return await svc.scan_repository(org_id, repo_id, scan_type)

    # ─── Observability (Volume 28) ───
    @router.post("/observability/metrics")
    async def ingest_metric(org_id: str = Query(...), name: str = Query(...), value: float = Query(...)):
        svc = registry.get("observability")
        if not svc: raise HTTPException(404, "Observability not available")
        return await svc.ingest_metric(org_id, name, value)

    @router.get("/observability/dashboards/{dashboard_id}")
    async def get_dashboard(org_id: str = Query(...), dashboard_id: str = ""):
        svc = registry.get("observability")
        if not svc: raise HTTPException(404, "Observability not available")
        return await svc.get_dashboard(org_id, dashboard_id)

    # ─── AI & Data Platform (Volume 29) ───
    @router.post("/ai/pipelines/run")
    async def run_pipeline(org_id: str = Query(...), pipeline_id: str = Query(...)):
        svc = registry.get("ai_data_platform")
        if not svc: raise HTTPException(404, "AI Platform not available")
        return await svc.run_pipeline(org_id, pipeline_id)

    @router.post("/ai/models/register")
    async def register_model(org_id: str = Query(...), name: str = Query(...), version: str = Query(...), uri: str = Query(...), framework: str = ""):
        svc = registry.get("ai_data_platform")
        if not svc: raise HTTPException(404, "AI Platform not available")
        return await svc.register_model(org_id, name, version, uri, framework)

    @router.post("/ai/embeddings/query")
    async def query_embeddings(org_id: str = Query(...), collection: str = Query(...), query: str = Query(...), top_k: int = 5):
        svc = registry.get("ai_data_platform")
        if not svc: raise HTTPException(404, "AI Platform not available")
        return await svc.query_embeddings(org_id, collection, query, top_k)

    # ─── Enterprise Platform (Volume 30) ───
    @router.post("/enterprise/organizations")
    async def create_organization(name: str = Query(...), domain: str = Query(...), plan: str = "free", owner_id: str = ""):
        svc = registry.get("enterprise_platform")
        if not svc: raise HTTPException(404, "Enterprise Platform not available")
        return await svc.create_organization(name, domain, plan, owner_id)

    @router.get("/enterprise/dashboard/{org_id}")
    async def get_dashboard(org_id: str = ""):
        svc = registry.get("enterprise_platform")
        if not svc: raise HTTPException(404, "Enterprise Platform not available")
        return await svc.get_global_dashboard(org_id)

    # ─── Data Lakehouse & Analytics (Volume 31) ───
    @router.post("/lakehouse/events")
    async def ingest_event(org_id: str = Query(...), event_type: str = Query(...),
                           payload: Optional[str] = Query(None)):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        import json
        return await svc.ingest_event(org_id, event_type, json.loads(payload) if payload else None)

    @router.post("/lakehouse/events/batch")
    async def ingest_batch(org_id: str = Query(...), events: str = Query(...)):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        import json
        return await svc.ingest_batch(org_id, json.loads(events))

    @router.post("/lakehouse/metrics")
    async def push_metric(org_id: str = Query(...), name: str = Query(...), value: float = Query(...)):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        return await svc.push_metric(org_id, name, value)

    @router.post("/lakehouse/batch")
    async def run_batch(org_id: str = Query(...), job: str = "daily"):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        return await svc.run_batch(org_id, job)

    @router.post("/lakehouse/tables")
    async def create_table(org_id: str = Query(...), name: str = Query(...),
                           columns: str = Query(...), partition_cols: str = ""):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        import json
        return await svc.create_table(org_id, name, json.loads(columns),
                                      json.loads(partition_cols) if partition_cols else None)

    @router.get("/lakehouse/query")
    async def query_analytics(org_id: str = Query(...), table: str = Query(...),
                              group_by: str = "", agg: str = "count",
                              filters: str = "", limit: int = 100):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        import json
        return await svc.query(org_id, table, group_by, agg,
                               json.loads(filters) if filters else None, limit)

    @router.get("/lakehouse/analytics/{kind}")
    async def analytics(org_id: str = Query(...), kind: str = ""):
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        handlers = {
            "ecommerce": svc.ecommerce,
            "ai": svc.ai_usage,
            "rag": svc.rag_metrics,
            "agents": svc.agent_performance,
            "finops": svc.finops_overview,
        }
        handler = handlers.get(kind)
        if not handler: raise HTTPException(404, f"unknown analytics kind: {kind}")
        return await handler(org_id)

    @router.get("/lakehouse/retention")
    async def retention_status():
        svc = registry.get("lakehouse")
        if not svc: raise HTTPException(404, "Lakehouse not available")
        return svc.retention_report()

    # ─── Multimodal AI & Computer Vision (Volume 32) ───
    @router.post("/multimodal/ingest")
    async def multimodal_ingest(request: Request, org_id: str = Query(...),
                                file_name: str = Query(...),
                                declared_mime: str = "",
                                source: str = "upload",
                                async_: bool = False):
        """Raw-bytes upload (body = file content)."""
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        data = await request.body()
        return await svc.ingest(org_id, file_name, data,
                                declared_mime=declared_mime, source=source,
                                async_=async_)

    @router.post("/multimodal/upload")
    async def multimodal_upload(org_id: str = Query(...), source: str = "upload",
                                declared_mime: str = "", async_: bool = False,
                                file: UploadFile = File(...)):
        """Multipart file upload."""
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        data = await file.read()
        return await svc.ingest(org_id, file.filename or "upload.bin", data,
                                declared_mime=declared_mime, source=source,
                                async_=async_)

    @router.get("/multimodal/ingest/{job_id}")
    async def multimodal_job(org_id: str = Query(...), job_id: str = ""):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.job(org_id, job_id)

    @router.get("/multimodal/assets")
    async def multimodal_assets(org_id: str = Query(...), modality: str = "",
                                limit: int = 100):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.list_assets(org_id, modality, limit)

    @router.delete("/multimodal/assets/{asset_id}")
    async def multimodal_delete(org_id: str = Query(...), asset_id: str = ""):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.delete_asset(org_id, asset_id)

    @router.get("/multimodal/search")
    async def multimodal_search(org_id: str = Query(...), query: str = Query(...),
                                limit: int = 8, modalities: str = ""):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.search(org_id, query, limit, modalities)

    @router.get("/multimodal/answer")
    async def multimodal_answer(org_id: str = Query(...), query: str = Query(...),
                                limit: int = 8, modalities: str = "",
                                generate: bool = True):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.answer(org_id, query, limit, modalities, generate)

    @router.get("/multimodal/usage")
    async def multimodal_usage(org_id: str = Query(...)):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.usage(org_id)

    @router.get("/multimodal/health")
    async def multimodal_health():
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return svc.health_check()
