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

# Import service modules to register volume services in the global registry
try:
    from app.release_engineering import service as _
except Exception as e: logger.debug("release_engineering: %s", e)
try:
    from app.rtc import service as _
except Exception as e: logger.debug("rtc: %s", e)
try:
    from app.aiops import service as _
except Exception as e: logger.debug("aiops: %s", e)
try:
    from app.security_compliance import service as _
except Exception as e: logger.debug("security_compliance: %s", e)
try:
    from app.observability import service as _
except Exception as e: logger.debug("observability: %s", e)
try:
    from app.ai_data_platform import service as _
except Exception as e: logger.debug("ai_data_platform: %s", e)
try:
    from app.enterprise_platform import service as _
except Exception as e: logger.debug("enterprise_platform: %s", e)
try:
    from app.lakehouse import service as _
except Exception as e: logger.debug("lakehouse: %s", e)
try:
    from app.multimodal import service as _
except Exception as e: logger.debug("multimodal: %s", e)
try:
    from app.automation import service as _
except Exception as e: logger.debug("automation: %s", e)
try:
    from app.evaluation import service as _
except Exception as e: logger.debug("evaluation: %s", e)

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
        return await svc.retention_report()

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

    @router.get("/multimodal/ledger")
    async def multimodal_ledger(org_id: str = "", limit: int = 100):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.ledger(org_id, limit)

    @router.post("/multimodal/screenshot")
    async def multimodal_screenshot(org_id: str = Query(...),
                                    url: str = Query(...),
                                    viewport: str = ""):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.capture_screenshot(org_id, url, viewport)

    @router.get("/multimodal/screenshots")
    async def multimodal_screenshots(org_id: str = "", limit: int = 100):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return {"screenshots": svc.screenshots.store.list(org_id, limit)}

    @router.get("/multimodal/comparisons")
    async def multimodal_comparisons(org_id: str = "", limit: int = 100):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.comparisons(org_id, limit)

    @router.get("/multimodal/compare/{baseline_id}/{candidate_id}")
    async def multimodal_compare(org_id: str = Query(...),
                                 baseline_id: str = "",
                                 candidate_id: str = ""):
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.compare_screenshots(org_id, baseline_id, candidate_id)

    @router.get("/multimodal/health")
    async def multimodal_health():
        svc = registry.get("multimodal")
        if not svc: raise HTTPException(404, "Multimodal not available")
        return await svc.health_check()

    # ─── Automation (Volume 33) ───
    def _automation():
        svc = registry.get("automation")
        if not svc: raise HTTPException(404, "Automation not available")
        return svc.gateway

    @router.post("/automation/workflows")
    async def automation_define(org_id: str = Query(...), definition: dict = None):
        gw = _automation()
        try:
            spec = gw.define(definition or {}, organization_id=org_id)
            return {"workflow_id": spec.workflow_id, "status": spec.status,
                    "version": spec.version}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.get("/automation/workflows")
    async def automation_list(org_id: str = ""):
        return {"workflows": _automation().list_workflows(org_id)}

    @router.get("/automation/workflows/{workflow_id}/dry-run")
    async def automation_dry_run(org_id: str = Query(...), workflow_id: str = ""):
        gw = _automation()
        try:
            return gw.dry_run(workflow_id, org_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/automation/workflows/{workflow_id}/publish")
    async def automation_publish(org_id: str = Query(...), workflow_id: str = ""):
        gw = _automation()
        try:
            return gw.publish(workflow_id, org_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/automation/workflows/{workflow_id}/run")
    async def automation_run(org_id: str = Query(...), workflow_id: str = "",
                             inputs: dict = None):
        gw = _automation()
        try:
            return gw.run(workflow_id, org_id, inputs=inputs or {})
        except KeyError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.get("/automation/executions")
    async def automation_executions(org_id: str = "", limit: int = 50):
        return {"executions": _automation().executions(org_id, limit)}

    @router.get("/automation/executions/{execution_id}")
    async def automation_execution(org_id: str = Query(...),
                                   execution_id: str = ""):
        gw = _automation()
        rec = gw.execution(execution_id, org_id)
        if rec is None:
            raise HTTPException(404, f"execution '{execution_id}' not found")
        return rec

    @router.post("/automation/approvals/{workflow_id}/{step_id}")
    async def automation_approve(org_id: str = Query(...),
                                 workflow_id: str = "",
                                 step_id: str = "",
                                 decision: str = Query("approved"),
                                 actor: str = "api_operator"):
        gw = _automation()
        if decision not in ("approved", "rejected"):
            raise HTTPException(400, "decision must be approved|rejected")
        req = gw.engine.approvals.decide(workflow_id, step_id, decision,
                                         actor=actor, organization_id=org_id)
        if req is None:
            raise HTTPException(404, "approval request not found")
        return req.to_dict()

    @router.post("/automation/ai/generate")
    async def automation_ai(prompt: str = Query(...), org_id: str = ""):
        return _automation().run_ai_generated(prompt, org_id)

    @router.post("/automation/webhook/{path:path}")
    async def automation_webhook(path: str, request: Request,
                                 timestamp: str = Query(...),
                                 signature: str = Query(...)):
        gw = _automation()
        body = await request.body()
        try:
            return gw.receive_webhook("/" + path, body, timestamp, signature)
        except Exception as exc:
            raise HTTPException(401, str(exc))

    @router.post("/automation/tick")
    async def automation_tick():
        return {"due": _automation().tick()}

    @router.get("/automation/health")
    async def automation_health():
        return _automation().health()

    # ─── AI Benchmarking & Evaluation (Volume 34) ───
    def _evaluation():
        svc = registry.get("evaluation")
        if not svc: raise HTTPException(404, "Evaluation not available")
        return svc.gateway

    # datasets
    @router.post("/evaluation/datasets")
    async def evaluation_create_dataset(name: str = Query(...),
                                        task_type: str = Query("qa"),
                                        description: str = Query(""),
                                        org_id: str = Query("")):
        gw = _evaluation()
        try:
            return gw.create_dataset(name, task_type, description,
                                     organization_id=org_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.get("/evaluation/datasets")
    async def evaluation_list_datasets(org_id: str = "", task_type: str = ""):
        return {"datasets": _evaluation().list_datasets(org_id, task_type)}

    @router.get("/evaluation/datasets/{dataset_id}")
    async def evaluation_get_dataset(dataset_id: str):
        gw = _evaluation()
        try:
            return gw.get_dataset(dataset_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/evaluation/datasets/{dataset_id}/versions")
    async def evaluation_add_version(dataset_id: str, examples: dict = None,
                                     notes: str = Query("")):
        """examples: {examples: [{input, expected_output, ...}]}"""
        gw = _evaluation()
        items = (examples or {}).get("examples", [])
        try:
            return gw.add_version(dataset_id, items, notes=notes)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @router.get("/evaluation/datasets/{dataset_id}/versions")
    async def evaluation_versions(dataset_id: str):
        gw = _evaluation()
        try:
            return {"versions": gw.datasets.list_versions(dataset_id)}
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/evaluation/datasets/{dataset_id}/versions/{version}")
    async def evaluation_get_version(dataset_id: str, version: int):
        gw = _evaluation()
        try:
            return gw.get_version(dataset_id, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/evaluation/datasets/{dataset_id}/publish")
    async def evaluation_publish(dataset_id: str, version: int = Query(0)):
        gw = _evaluation()
        try:
            return gw.publish_version(dataset_id, version or None)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/evaluation/datasets/{dataset_id}/clone")
    async def evaluation_clone(dataset_id: str, new_name: str = Query(""),
                               org_id: str = Query("")):
        gw = _evaluation()
        try:
            return gw.clone_dataset(dataset_id, new_name, org_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/evaluation/datasets/{dataset_id}/archive")
    async def evaluation_archive(dataset_id: str):
        gw = _evaluation()
        try:
            return gw.archive_dataset(dataset_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.post("/evaluation/datasets/{dataset_id}/rollback")
    async def evaluation_rollback(dataset_id: str, version: int = Query(...)):
        gw = _evaluation()
        try:
            return gw.rollback_version(dataset_id, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/evaluation/datasets/{dataset_id}/diff")
    async def evaluation_diff(dataset_id: str, a: int = Query(...),
                              b: int = Query(...)):
        gw = _evaluation()
        try:
            return gw.diff_versions(dataset_id, a, b)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/evaluation/datasets/{dataset_id}/lineage")
    async def evaluation_lineage(dataset_id: str, version: int = Query(0)):
        gw = _evaluation()
        try:
            return gw.dataset_lineage(dataset_id, version or None)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    # benchmarks
    @router.post("/evaluation/runs")
    async def evaluation_run(dataset_id: str = Query(...),
                             model: str = Query(""),
                             dataset_version: int = Query(0),
                             target_type: str = Query("model"),
                             org_id: str = Query(""),
                             prompt_version: str = Query("")):
        gw = _evaluation()
        try:
            return gw.run_benchmark(
                dataset_id, model=model,
                dataset_version=dataset_version or None,
                target_type=target_type, organization_id=org_id,
                prompt_version=prompt_version)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @router.get("/evaluation/runs")
    async def evaluation_runs(org_id: str = "", limit: int = 50):
        return {"runs": _evaluation().list_runs(org_id, limit)}

    @router.get("/evaluation/runs/{run_id}")
    async def evaluation_run_detail(run_id: str):
        gw = _evaluation()
        try:
            return gw.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/evaluation/runs/{run_id}/report")
    async def evaluation_run_report(run_id: str, format: str = Query("json")):
        gw = _evaluation()
        try:
            report = gw.report(run_id)
            if format == "markdown":
                return {"markdown": gw.markdown_report(report)}
            return report
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    # pairwise
    @router.post("/evaluation/pairwise")
    async def evaluation_pairwise(a_label: str = Query(...),
                                  b_label: str = Query(...),
                                  examples: dict = None,
                                  dataset_id: str = Query("")):
        gw = _evaluation()
        items = (examples or {}).get("examples", [])
        try:
            return gw.compare_pairwise(a_label, b_label, items,
                                       dataset_id=dataset_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.get("/evaluation/pairwise")
    async def evaluation_pairwise_list(limit: int = 50):
        return {"comparisons": _evaluation().list_pairwise(limit)}

    # judges + calibration
    @router.post("/evaluation/judge")
    async def evaluation_judge(prompt: str = Query(...),
                               output: str = Query(...),
                               reference: str = Query(""),
                               model: str = Query("")):
        return _evaluation().judge(prompt, output, reference, model)

    @router.post("/evaluation/calibrate")
    async def evaluation_calibrate(judge_scores: str = Query(...),
                                   human_scores: str = Query("")):
        gw = _evaluation()
        import json
        js = json.loads(judge_scores)
        hs = json.loads(human_scores) if human_scores else None
        return gw.calibrate(js, hs)

    # human review
    @router.post("/evaluation/reviews")
    async def evaluation_add_review(run_id: str = Query(...),
                                    example_id: str = Query(...),
                                    reviewer: str = Query(""),
                                    scores: str = Query(""),
                                    preference: str = Query("")):
        gw = _evaluation()
        import json
        parsed = json.loads(scores) if scores else None
        return gw.add_review(run_id, example_id, reviewer, parsed, preference)

    @router.get("/evaluation/reviews")
    async def evaluation_reviews(run_id: str = "", example_id: str = ""):
        return {"reviews": _evaluation().list_reviews(run_id, example_id)}

    @router.get("/evaluation/reviews/{run_id}/report")
    async def evaluation_review_report(run_id: str):
        return _evaluation().review_report(run_id)

    @router.get("/evaluation/reviews/{run_id}/reliability")
    async def evaluation_reliability(run_id: str):
        return _evaluation().reliability(run_id)

    # metrics
    @router.get("/evaluation/metrics/rag")
    async def evaluation_rag_metrics(relevant: str = Query(...),
                                     retrieved: str = Query(...),
                                     k: int = Query(5)):
        import json
        return _evaluation().rag_metrics(json.loads(relevant),
                                         json.loads(retrieved), k)

    @router.get("/evaluation/metrics/rag-generation")
    async def evaluation_rag_generation(claims_supported: int = Query(...),
                                        claims_total: int = Query(...),
                                        unsupported_claims: int = Query(0),
                                        useful_sentences: int = Query(0),
                                        context_sentences: int = Query(0),
                                        correct_citations: int = Query(0),
                                        total_citations: int = Query(0),
                                        cited_claims: int = Query(0)):
        return _evaluation().rag_generation(
            claims_supported, claims_total, unsupported_claims,
            useful_sentences, context_sentences, correct_citations,
            total_citations, cited_claims)

    @router.post("/evaluation/metrics/code")
    async def evaluation_code(expected_code: str = Query(...),
                              actual_code: str = Query(...)):
        return _evaluation().code_generation(expected_code, actual_code)

    # regression gates
    @router.post("/evaluation/gates")
    async def evaluation_gate(baseline_run_id: str = Query(...),
                              candidate_run_id: str = Query(...)):
        gw = _evaluation()
        try:
            return gw.gate(baseline_run_id, candidate_run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/evaluation/gates")
    async def evaluation_gates(limit: int = 50):
        return {"gates": _evaluation().list_gates(limit)}

    @router.get("/evaluation/gates/{gate_id}")
    async def evaluation_gate_detail(gate_id: str):
        gw = _evaluation()
        try:
            return gw.get_gate(gate_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    # integrations + health
    @router.get("/evaluation/multimodal")
    async def evaluation_multimodal(org_id: str = Query("")):
        return _evaluation().multimodal_health()

    @router.get("/evaluation/automation")
    async def evaluation_automation():
        return _evaluation().automation_health()

    @router.get("/evaluation/health")
    async def evaluation_health():
        return _evaluation().health()
