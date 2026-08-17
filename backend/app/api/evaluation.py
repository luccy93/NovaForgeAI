"""Dataset & Evaluation API — Volume 34: AI Benchmarking & Evaluation Platform.

Endpoints for dataset management, benchmark execution, model comparison,
and evaluation metrics. Integrates with the existing evaluation modules
(datasets, benchmark, metrics, judges, regression, code_eval, etc.).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Optional, Any

from app.api.auth import _get_current_user
from app.core.database import get_db

router = APIRouter(tags=["Datasets & Evaluations"])


# ─── Request/Response Models ───────────────────────────────────────────────

class DatasetCreateRequest(BaseModel):
    name: str
    task_type: str = "qa"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionCreateRequest(BaseModel):
    examples: list[dict[str, Any]]
    notes: str = ""


class BenchmarkRunRequest(BaseModel):
    dataset_id: str
    model: str = ""
    prompt_version: str = ""
    agent_version: str = ""
    rag_version: str = ""
    provider: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class ComparisonRequest(BaseModel):
    run_id_a: str
    run_id_b: str


class RegressionCheckRequest(BaseModel):
    dataset_id: str
    baseline_run_id: str
    candidate_run_id: str
    threshold: float = 0.05


# ─── Helpers ───────────────────────────────────────────────────────────────

def _get_dataset_manager():
    from app.evaluation.datasets import DatasetManager
    return DatasetManager()


def _get_benchmark_runner():
    from app.evaluation.benchmark import BenchmarkRunner
    return BenchmarkRunner()


def _get_regression_engine():
    from app.evaluation.regression import RegressionEngine
    return RegressionEngine()


# ─── Dataset Endpoints ─────────────────────────────────────────────────────

@router.post("/datasets", status_code=201)
async def create_dataset(
    req: DatasetCreateRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    org_id = getattr(current_user, "organization_id", "default")
    try:
        ds = dm.create(
            name=req.name,
            task_type=req.task_type,
            description=req.description,
            organization_id=org_id,
            owner=getattr(current_user, "id", ""),
            tags=req.tags,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return ds


@router.get("/datasets")
async def list_datasets(
    task_type: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    org_id = getattr(current_user, "organization_id", "default")
    datasets = dm.list_datasets(organization_id=org_id, task_type=task_type or "")
    return {"datasets": datasets, "total": len(datasets)}


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.get(dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        dm.delete(dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"deleted": True, "dataset_id": dataset_id}


# ─── Version Endpoints ─────────────────────────────────────────────────────

@router.post("/datasets/{dataset_id}/versions", status_code=201)
async def create_version(
    dataset_id: str,
    req: VersionCreateRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        version = dm.add_version(
            dataset_id,
            req.examples,
            notes=req.notes,
            created_by=getattr(current_user, "id", ""),
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return version


@router.get("/datasets/{dataset_id}/versions")
async def list_versions(
    dataset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        versions = dm.list_versions(dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"versions": versions, "total": len(versions)}


@router.get("/datasets/{dataset_id}/versions/{version}")
async def get_version(
    dataset_id: str,
    version: int,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.get_version(dataset_id, version)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/datasets/{dataset_id}/diff")
async def diff_versions(
    dataset_id: str,
    version_a: int = Query(...),
    version_b: int = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.diff(dataset_id, version_a, version_b)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/datasets/{dataset_id}/compare")
async def compare_versions(
    dataset_id: str,
    version_a: int = Query(...),
    version_b: int = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.compare(dataset_id, version_a, version_b)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/datasets/{dataset_id}/lineage")
async def get_lineage(
    dataset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.lineage(dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/datasets/{dataset_id}/clone", status_code=201)
async def clone_dataset(
    dataset_id: str,
    target_name: str = Body("", embed=True),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    org_id = getattr(current_user, "organization_id", "default")
    try:
        return dm.clone(dataset_id, new_name=target_name, organization_id=org_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/datasets/{dataset_id}/publish")
async def publish_dataset(
    dataset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.publish(dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/datasets/{dataset_id}/archive")
async def archive_dataset(
    dataset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.archive(dataset_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/datasets/{dataset_id}/rollback")
async def rollback_dataset(
    dataset_id: str,
    version: int = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    dm = _get_dataset_manager()
    try:
        return dm.rollback(dataset_id, version)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Benchmark Endpoints ──────────────────────────────────────────────────

@router.post("/benchmarks/run", status_code=201)
async def run_benchmark(
    req: BenchmarkRunRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    br = _get_benchmark_runner()
    org_id = getattr(current_user, "organization_id", "default")
    try:
        run = br.run(
            dataset_id=req.dataset_id,
            model=req.model,
            prompt_version=req.prompt_version,
            agent_version=req.agent_version,
            rag_version=req.rag_version,
            provider=req.provider,
            config=req.config,
            organization_id=org_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return run


@router.get("/benchmarks/runs")
async def list_benchmark_runs(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    br = _get_benchmark_runner()
    runs = br.list_runs()
    return {"runs": runs, "total": len(runs)}


@router.get("/benchmarks/runs/{run_id}")
async def get_benchmark_run(
    run_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    br = _get_benchmark_runner()
    try:
        return br.get_run(run_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Metrics Endpoints ─────────────────────────────────────────────────────

@router.get("/metrics/report")
async def metrics_report(
    run_id: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.metrics import aggregate, retrieval_report
    from app.evaluation.benchmark import BenchmarkRunner
    br = _get_benchmark_runner()
    try:
        run = br.get_run(run_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run_id": run_id, "results": run.get("results", {})}


@router.get("/metrics/retrieval")
async def retrieval_metrics(
    relevant: list[str] = Query(...),
    retrieved: list[str] = Query(...),
    k: int = Query(10),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.metrics import retrieval_report
    report = retrieval_report(relevant, retrieved, k)
    return report


@router.get("/metrics/rag")
async def rag_metrics(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.metrics import faithfulness, hallucination_rate
    return {
        "faithfulness": faithfulness([], []),
        "hallucination_rate": hallucination_rate([], []),
    }


# ─── Regression Endpoints ─────────────────────────────────────────────────

@router.post("/regression/check", status_code=201)
async def check_regression(
    req: RegressionCheckRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    re = _get_regression_engine()
    try:
        result = re.check(
            dataset_id=req.dataset_id,
            baseline_run_id=req.baseline_run_id,
            candidate_run_id=req.candidate_run_id,
            threshold=req.threshold,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


# ─── Code Evaluation Endpoints ─────────────────────────────────────────────

@router.post("/code-eval/generation")
async def code_generation_eval(
    predictions: list[str] = Body(...),
    references: list[str] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.code_eval import code_generation_report
    return code_generation_report(predictions, references)


@router.post("/code-eval/repair")
async def code_repair_eval(
    predictions: list[str] = Body(...),
    references: list[str] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.code_eval import code_repair_report
    return code_repair_report(predictions, references)


@router.post("/code-eval/review")
async def code_review_eval(
    predictions: list[str] = Body(...),
    references: list[str] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.code_eval import code_review_report
    return code_review_report(predictions, references)


@router.post("/code-eval/security")
async def security_eval(
    predictions: list[str] = Body(...),
    references: list[str] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.evaluation.code_eval import security_eval_report
    return security_eval_report(predictions, references)


@router.get("/health")
async def evaluation_health(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    return {
        "status": "healthy",
        "version": "34.0",
        "modules": {
            "datasets": True,
            "benchmark": True,
            "metrics": True,
            "regression": True,
            "code_eval": True,
        },
    }
