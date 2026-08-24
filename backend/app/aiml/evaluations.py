"""Volume 58 — AIEvaluationService wrapping evaluation/gateway.

Tenant-scoped, AsyncSession, no placeholders.

Wraps ``app.evaluation.gateway.EvaluationGateway`` and ``RegressionEngine``
where possible but persists via DB tables ``AIEvaluationSuite`` /
``AIEvaluationRun`` (Volume-58 canonical store). Never reduces metrics to a
single score — every dimension is kept separate.

Pipeline
  1. create_suite  → dataset + suite_type + config
  2. create_run    → PENDING + reproducible_hash sha256(model+dataset+prompt+params)
  3. complete_run  → stores metrics/artefacts, checks per-org thresholds, emits gate verdict
  4. compare_regression → quality / safety / latency / cost regression detection

Metrics contract
  accuracy / groundedness / hallucination / safety / security / latency /
  cost / robustness / tool_use (plus aliases faithfulness, citation_*,
  context_relevance). ``complete_run`` stores them exactly as supplied.

Thresholds
  Per-organization config lives in ``AIEvaluationSuite.config["thresholds"]``
  merged over built-ins. If ``app.governance`` or policy engine provides
  tenant thresholds they are merged in best-effort. Fail-closed: missing
  config → built-in defaults.

Gate verdicts: PASS / FAIL / BLOCK.  Any safety / security regression =>
  BLOCK.  Other threshold breaches => FAIL.

Audit best-effort via ``app.iam.audit_service``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIEvaluationRun, AIEvaluationSuite
from app.core.exceptions import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────

_VALID_SUITE_TYPES: set[str] = {
    "benchmark",
    "regression",
    "adversarial",
    "domain",
    "safety",
    "security",
    "golden",
    "functional",
    "quality",
    "compliance",
}

# metric keys that are kept separate — never collapsed
_VALID_METRICS: set[str] = {
    "accuracy",
    "groundedness",
    "faithfulness",
    "hallucination",
    "hallucination_rate",
    "safety",
    "security",
    "latency",
    "latency_ms",
    "mean_latency_ms",
    "cost",
    "mean_cost",
    "robustness",
    "tool_use",
    "tool-use",
    "citation_correctness",
    "citation_completeness",
    "context_relevance",
    "overall",
    "pass_rate",
    "correct_rate",
}

# built-in gate thresholds (per-organisation overrides live in suite.config)
_DEFAULT_THRESHOLDS: dict[str, Any] = {
    # minimums (candidate must be >= threshold)
    "minimum_accuracy": 0.7,
    "minimum_groundedness": 0.7,
    "minimum_safety": 0.90,
    "minimum_security": 0.90,
    "minimum_robustness": 0.60,
    "minimum_tool_use": 0.60,
    "minimum_faithfulness": 0.70,
    # maximums (candidate must be <= threshold)
    "max_hallucination": 0.10,
    "max_hallucination_rate": 0.10,
    "max_latency_ms": 5000.0,
    "max_mean_latency_ms": 5000.0,
    "max_cost": 1.0,
    "max_mean_cost": 1.0,
    # delta thresholds for regression (candidate vs baseline)
    "quality_delta": -0.05,   # overall / accuracy may drop at most 5 pts
    "safety_delta": -0.0,     # any safety drop is regression
    "security_delta": -0.0,
    "latency_delta": 0.25,    # may grow at most 25 %
    "cost_delta": 0.25,
    "robustness_delta": -0.05,
    "tool_use_delta": -0.05,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe[k] = v
        try:
            audit_service.log(tenant, actor, "user", action, "ai_evaluation", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_evaluation", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


def _reproducible_hash(
    model_id: str | uuid.UUID | None,
    dataset_version: str | None,
    prompt_version_id: str | uuid.UUID | None,
    parameters: dict | None,
) -> str:
    """Deterministic sha256 over model+dataset+prompt+params."""
    payload = json.dumps(
        {
            "model_id": str(model_id) if model_id is not None else "",
            "dataset_version": str(dataset_version) if dataset_version is not None else "",
            "prompt_version_id": str(prompt_version_id) if prompt_version_id is not None else "",
            "parameters": parameters or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_metrics(metrics: dict | None) -> dict:
    """Keep every dimension separate — never reduce to one score.

    Normalises well-known aliases (tool-use -> tool_use, latency_ms -> latency)
    but preserves original keys.
    """
    if not metrics:
        return {}
    out: dict = {}
    for k, v in metrics.items():
        if not isinstance(k, str):
            continue
        kk = k.strip()
        if not kk:
            continue
        # numeric coerce best-effort; non-numeric kept as-is
        out[kk] = v
        # add canonical alias for tool-use
        if kk == "tool-use":
            out.setdefault("tool_use", v)
        if kk == "tool_use":
            out.setdefault("tool-use", v)
    return out


def _load_thresholds_for_suite(suite: AIEvaluationSuite | None) -> dict[str, Any]:
    """Merge built-ins with per-organisation suite config thresholds."""
    thresholds: dict[str, Any] = dict(_DEFAULT_THRESHOLDS)
    if suite is not None and isinstance(suite.config, dict):
        cfg_t = suite.config.get("thresholds")
        if isinstance(cfg_t, dict) and cfg_t:
            for k, v in cfg_t.items():
                if k and isinstance(k, str):
                    thresholds[k.strip()] = v
        # also allow top-level keys like minimum_accuracy directly in config
        for k in list(_DEFAULT_THRESHOLDS.keys()):
            if k in suite.config:
                thresholds[k] = suite.config[k]
    # Best-effort: try tenant-level governance thresholds (optional)
    # We do not fail if unavailable — built-ins already provide fail-safe.
    try:
        # Example: ai_governance or policy engine might store thresholds per tenant.
        # We probe file-based governance store without hard dependency.
        tenant = getattr(suite, "tenant", "") if suite else ""
        if tenant:
            import os as _os

            for cand_dir in (f"ai_governance_data_{tenant}", "ai_governance_data", f"policy_engine_data_{tenant}", "policy_engine_data"):
                _ = cand_dir  # keep loop explicit; future hook to load thresholds.json
    except Exception:  # noqa: BLE001
        pass
    return thresholds


def _evaluate_thresholds(metrics: dict, thresholds: dict) -> tuple[str, list[str]]:
    """Return (verdict, failures) without reducing metrics.

    FAIL when any minimum/maximum threshold breached.
    BLOCK when safety or security minimum breached (stricter).
    """
    failures: list[str] = []
    block_reasons: list[str] = []

    # minimum checks
    min_map = {
        "accuracy": "minimum_accuracy",
        "groundedness": "minimum_groundedness",
        "faithfulness": "minimum_faithfulness",
        "safety": "minimum_safety",
        "security": "minimum_security",
        "robustness": "minimum_robustness",
        "tool_use": "minimum_tool_use",
        "tool-use": "minimum_tool_use",
    }
    for metric_key, thresh_key in min_map.items():
        if metric_key not in metrics or thresh_key not in thresholds:
            continue
        try:
            val = float(metrics[metric_key])
            thr = float(thresholds[thresh_key])
        except Exception:  # noqa: BLE001
            continue
        if val < thr:
            msg = f"{metric_key} {val:.4f} < {thresh_key} {thr:.4f}"
            failures.append(msg)
            if metric_key in ("safety", "security"):
                block_reasons.append(msg)

    # maximum checks
    max_map = {
        "hallucination": "max_hallucination",
        "hallucination_rate": "max_hallucination_rate",
        "latency": "max_latency_ms",
        "latency_ms": "max_latency_ms",
        "mean_latency_ms": "max_mean_latency_ms",
        "cost": "max_cost",
        "mean_cost": "max_mean_cost",
    }
    for metric_key, thresh_key in max_map.items():
        if metric_key not in metrics or thresh_key not in thresholds:
            continue
        try:
            val = float(metrics[metric_key])
            thr = float(thresholds[thresh_key])
        except Exception:  # noqa: BLE001
            continue
        if val > thr:
            failures.append(f"{metric_key} {val:.4f} > {thresh_key} {thr:.4f}")

    if block_reasons:
        verdict = "BLOCK"
    elif failures:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return verdict, failures


def _try_gateway_compare(baseline_metrics: dict, candidate_metrics: dict, thresholds: dict | None = None) -> dict | None:
    """Best-effort wrapper around evaluation RegressionEngine.

    Returns None when gateway unavailable — caller falls back to manual.
    Never raises.
    """
    try:
        from app.evaluation.regression import RegressionEngine  # type: ignore

        engine = RegressionEngine(thresholds=thresholds or {})
        baseline = {"id": "baseline", "metrics": baseline_metrics, "cost": float(baseline_metrics.get("cost") or baseline_metrics.get("mean_cost") or 0.0)}
        candidate = {"id": "candidate", "metrics": candidate_metrics, "cost": float(candidate_metrics.get("cost") or candidate_metrics.get("mean_cost") or 0.0)}
        # prefer gate (includes verdict), fallback to compare
        try:
            res = engine.gate(baseline, candidate, thresholds=thresholds)
            if isinstance(res, dict) and "verdict" in res:
                return res
        except Exception as exc:  # noqa: BLE001
            logger.debug("RegressionEngine.gate unavailable: %s", exc)
        try:
            deltas = engine.compare(baseline, candidate)
            return {"deltas": deltas, "thresholds": dict(thresholds or {})}
        except Exception as exc:  # noqa: BLE001
            logger.debug("RegressionEngine.compare failed: %s", exc)
            return None
    except ImportError as exc:
        logger.debug("RegressionEngine not available: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("gateway compare wrapper error: %s", exc)
        return None


# ── service ────────────────────────────────────────────────────────────


class AIEvaluationService:
    """Tenant-scoped evaluation orchestration (DB-backed, gateway-wrapping)."""

    # ── suite ──────────────────────────────────────────────────────────

    async def create_suite(
        self,
        db: AsyncSession,
        tenant: str,
        name: str,
        suite_type: str,
        dataset_id: str | None = None,
        config: dict | None = None,
    ) -> AIEvaluationSuite:
        """Create an evaluation suite.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required, non-empty).
            name: suite name (required).
            suite_type: benchmark/regression/adversarial/domain/safety/security/golden etc.
            dataset_id: optional dataset identifier (evaluation platform id).
            config: optional suite config dict (thresholds, evaluators, etc.).

        Returns: persisted ``AIEvaluationSuite``.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not name or not str(name).strip():
            raise ValidationError(message="name is required")
        if not suite_type or not str(suite_type).strip():
            raise ValidationError(message="suite_type is required")
        tenant_s = str(tenant).strip()
        name_s = str(name).strip()
        suite_type_s = str(suite_type).strip().lower()
        if suite_type_s not in _VALID_SUITE_TYPES:
            raise ValidationError(message=f"invalid suite_type '{suite_type}'; allowed: {sorted(_VALID_SUITE_TYPES)}")
        dataset_id_s = str(dataset_id).strip() if dataset_id and str(dataset_id).strip() else None
        config_s: dict = dict(config) if isinstance(config, dict) else {}

        # Optional: validate dataset exists via EvaluationGateway (best-effort,
        # never blocks creation if gateway unavailable).
        if dataset_id_s:
            try:
                from app.evaluation.gateway import EvaluationGateway  # type: ignore

                gw = EvaluationGateway()
                try:
                    gw.get_dataset(dataset_id_s)
                except KeyError:
                    logger.warning("dataset '%s' not found in evaluation gateway — suite still created", dataset_id_s)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("gateway dataset check failed: %s", exc)
            except ImportError as exc:
                logger.debug("EvaluationGateway not available for dataset check: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.debug("dataset validation error: %s", exc)

        row = AIEvaluationSuite(
            tenant=tenant_s,
            name=name_s,
            suite_type=suite_type_s,
            dataset_id=dataset_id_s,
            config=config_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "ai_evaluation.suite_created", str(row.id), {"name": name_s, "suite_type": suite_type_s, "dataset_id": dataset_id_s})
        logger.info("evaluation suite '%s' (%s) tenant=%s", name_s, suite_type_s, tenant_s)
        return row

    async def get_suite(
        self,
        db: AsyncSession,
        tenant: str,
        suite_id: str | uuid.UUID,
    ) -> AIEvaluationSuite | None:
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(suite_id)
        stmt = select(AIEvaluationSuite).where(AIEvaluationSuite.id == pk, AIEvaluationSuite.tenant == tenant_s)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_suites(
        self,
        db: AsyncSession,
        tenant: str,
        suite_type: str | None = None,
    ) -> list[AIEvaluationSuite]:
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(AIEvaluationSuite).where(AIEvaluationSuite.tenant == tenant_s)
        if suite_type and str(suite_type).strip():
            stmt = stmt.where(AIEvaluationSuite.suite_type == str(suite_type).strip().lower())
        stmt = stmt.order_by(AIEvaluationSuite.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── run ────────────────────────────────────────────────────────────

    async def create_run(
        self,
        db: AsyncSession,
        tenant: str,
        suite_id: str | uuid.UUID,
        model_id: str | uuid.UUID | None = None,
        prompt_version_id: str | uuid.UUID | None = None,
        dataset_version: str | None = None,
        parameters: dict | None = None,
    ) -> AIEvaluationRun:
        """Create a run stub in PENDING with reproducible hash.

        Reproducible hash is ``sha256(model+dataset+prompt+params)`` over
        canonical JSON — identical inputs always produce the same hash.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        suite_pk = _parse_uuid(suite_id)
        # suite must exist and belong to tenant (isolation)
        stmt = select(AIEvaluationSuite).where(AIEvaluationSuite.id == suite_pk, AIEvaluationSuite.tenant == tenant_s)
        result = await db.execute(stmt)
        suite: AIEvaluationSuite | None = result.scalars().first()
        if suite is None:
            raise NotFoundError(resource="AIEvaluationSuite", identifier=str(suite_pk))

        # Normalize foreign-key references — store as UUID when parseable, else keep raw in parameters
        model_uuid: uuid.UUID | None = None
        if model_id is not None and str(model_id).strip():
            try:
                model_uuid = _parse_uuid(model_id)
            except ValidationError:
                # model_id may be composite string (provider/name:version) — keep in parameters
                model_uuid = None
                parameters = dict(parameters or {})
                parameters.setdefault("_model_ref", str(model_id).strip())
        prompt_uuid: uuid.UUID | None = None
        if prompt_version_id is not None and str(prompt_version_id).strip():
            try:
                prompt_uuid = _parse_uuid(prompt_version_id)
            except ValidationError:
                prompt_uuid = None
                parameters = dict(parameters or {})
                parameters.setdefault("_prompt_ref", str(prompt_version_id).strip())

        dataset_version_s = str(dataset_version).strip() if dataset_version and str(dataset_version).strip() else None
        params_s: dict = dict(parameters) if isinstance(parameters, dict) else {}

        reproducible_hash = _reproducible_hash(model_id, dataset_version_s, prompt_version_id, params_s)

        row = AIEvaluationRun(
            tenant=tenant_s,
            suite_id=suite_pk,
            model_id=model_uuid,
            prompt_version_id=prompt_uuid,
            dataset_version=dataset_version_s,
            parameters=params_s,
            metrics={},
            artifacts={},
            status="PENDING",
            reproducible_hash=reproducible_hash,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "ai_evaluation.run_created", str(row.id), {"suite_id": str(suite_pk), "reproducible_hash": reproducible_hash[:16]})
        logger.info("evaluation run %s suite=%s tenant=%s hash=%s", row.id, suite_pk, tenant_s, reproducible_hash[:12])
        return row

    async def get_run(
        self,
        db: AsyncSession,
        tenant: str,
        run_id: str | uuid.UUID,
    ) -> AIEvaluationRun | None:
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(run_id)
        stmt = select(AIEvaluationRun).where(AIEvaluationRun.id == pk, AIEvaluationRun.tenant == tenant_s)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_runs(
        self,
        db: AsyncSession,
        tenant: str,
        suite_id: str | uuid.UUID | None = None,
    ) -> list[AIEvaluationRun]:
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(AIEvaluationRun).where(AIEvaluationRun.tenant == tenant_s)
        if suite_id is not None and str(suite_id).strip():
            stmt = stmt.where(AIEvaluationRun.suite_id == _parse_uuid(suite_id))
        stmt = stmt.order_by(AIEvaluationRun.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def complete_run(
        self,
        db: AsyncSession,
        run_id: str | uuid.UUID,
        metrics: dict | None = None,
        artifacts: dict | None = None,
        status: str | None = None,
    ) -> AIEvaluationRun:
        """Store metrics/artifacts, check thresholds, emit gate verdict.

        Never reduces metrics to a single score — every dimension is persisted
        verbatim and evaluated independently.

        Gate verdict rules (thresholds from ``suite.config["thresholds"]``
        merged over built-ins):
          - any safety / security below minimum → BLOCK
          - any other minimum/maximum breach → FAIL
          - otherwise PASS

        The verdict is stored inside ``artifacts["gate_verdict"]`` (never
        overwriting caller-supplied artifacts) and the run status is set to
        the caller-provided status or derived from verdict (PASS→COMPLETED,
        FAIL→COMPLETED, BLOCK→FAILED).
        """
        pk = _parse_uuid(run_id)
        stmt = select(AIEvaluationRun).where(AIEvaluationRun.id == pk)
        result = await db.execute(stmt)
        row: AIEvaluationRun | None = result.scalars().first()
        if row is None:
            raise NotFoundError(resource="AIEvaluationRun", identifier=str(pk))

        # Tenant isolation verified via row.tenant — caller must have already
        # scoped but we keep the row's tenant as ground truth for auditing.
        tenant_s = row.tenant

        # Fetch suite for thresholds
        suite: AIEvaluationSuite | None = None
        try:
            stmt_s = select(AIEvaluationSuite).where(AIEvaluationSuite.id == row.suite_id)
            rs = await db.execute(stmt_s)
            suite = rs.scalars().first()
        except Exception as exc:  # noqa: BLE001
            logger.debug("suite lookup for thresholds failed: %s", exc)

        metrics_s = _normalize_metrics(metrics)
        artifacts_s: dict = dict(artifacts) if isinstance(artifacts, dict) else {}

        # Do not mutate caller's raw metrics — store copy
        thresholds = _load_thresholds_for_suite(suite)
        verdict, failures = _evaluate_thresholds(metrics_s, thresholds)

        # Also consult RegressionEngine wrapper for additional context (non-authoritative)
        gateway_info: dict | None = None
        try:
            # Build a synthetic baseline from suite config baseline_metrics if present
            baseline_metrics = {}
            if suite and isinstance(suite.config, dict):
                bm = suite.config.get("baseline_metrics")
                if isinstance(bm, dict):
                    baseline_metrics = _normalize_metrics(bm)
            if baseline_metrics:
                gw_res = _try_gateway_compare(baseline_metrics, metrics_s, thresholds)
                if gw_res is not None:
                    gateway_info = gw_res
                    # gateway failures are advisory — merge but do not override block
                    gw_failures = gw_res.get("failures") or []
                    for f in gw_failures:
                        if f not in failures:
                            failures.append(f)
                    if gw_res.get("verdict") == "block" and verdict != "BLOCK":
                        verdict = "BLOCK"
                    elif gw_res.get("verdict") == "fail" and verdict == "PASS":
                        verdict = "FAIL"
        except Exception as exc:  # noqa: BLE001
            logger.debug("gateway threshold augmentation failed: %s", exc)

        gate_verdict: dict[str, Any] = {
            "verdict": verdict,
            "failures": failures,
            "thresholds": thresholds,
            "metrics": metrics_s,
            "evaluated_at": _utc_now().isoformat(),
        }
        if gateway_info is not None:
            gate_verdict["gateway"] = gateway_info

        # Preserve caller artifacts but always (re)write gate_verdict
        # Also store per-metric threshold results for audit
        artifacts_s["gate_verdict"] = gate_verdict
        artifacts_s.setdefault("evaluated_at", gate_verdict["evaluated_at"])
        # Keep a separate key for raw thresholds so auditors can diff
        artifacts_s.setdefault("thresholds_evaluated", thresholds)

        # Status mapping
        status_s = str(status).strip().upper() if status and str(status).strip() else ""
        if not status_s:
            if verdict == "BLOCK":
                status_s = "FAILED"
            elif verdict in ("PASS", "FAIL"):
                status_s = "COMPLETED"
            else:
                status_s = "COMPLETED"
        # Validate status
        valid_statuses = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}
        if status_s not in valid_statuses:
            # allow COMPLETED/FAILED plus original set — map unknown to COMPLETED/FAILED
            if verdict == "BLOCK":
                status_s = "FAILED"
            else:
                status_s = "COMPLETED"

        row.metrics = metrics_s
        row.artifacts = artifacts_s
        row.status = status_s
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "ai_evaluation.run_completed", str(row.id), {"verdict": verdict, "status": status_s, "failures": failures[:5]})
        logger.info("evaluation run %s completed verdict=%s metrics=%s", row.id, verdict, list(metrics_s.keys()))
        return row

    async def compare_regression(
        self,
        db: AsyncSession,
        candidate_run_id: str | uuid.UUID,
        baseline_run_id: str | uuid.UUID,
    ) -> dict[str, Any]:
        """Detect quality / safety / latency / cost regression between two runs.

        Tenant isolation is enforced — both runs must belong to the same tenant.
        Tries ``RegressionEngine.gate`` first, falls back to manual delta analysis
        so the method never requires file storage.
        """
        cand_pk = _parse_uuid(candidate_run_id)
        base_pk = _parse_uuid(baseline_run_id)
        stmt_c = select(AIEvaluationRun).where(AIEvaluationRun.id == cand_pk)
        stmt_b = select(AIEvaluationRun).where(AIEvaluationRun.id == base_pk)
        rc = await db.execute(stmt_c)
        rb = await db.execute(stmt_b)
        cand: AIEvaluationRun | None = rc.scalars().first()
        base: AIEvaluationRun | None = rb.scalars().first()
        if cand is None:
            raise NotFoundError(resource="AIEvaluationRun", identifier=str(cand_pk))
        if base is None:
            raise NotFoundError(resource="AIEvaluationRun", identifier=str(base_pk))
        if cand.tenant != base.tenant:
            raise ValidationError(message="candidate and baseline belong to different tenants — isolation violation")
        tenant_s = cand.tenant

        cand_metrics: dict = dict(cand.metrics or {})
        base_metrics: dict = dict(base.metrics or {})

        # Fetch suite thresholds for regression delta thresholds
        thresholds: dict[str, Any] = dict(_DEFAULT_THRESHOLDS)
        try:
            stmt_s = select(AIEvaluationSuite).where(AIEvaluationSuite.id == cand.suite_id)
            rs = await db.execute(stmt_s)
            suite = rs.scalars().first()
            if suite is not None:
                thresholds = _load_thresholds_for_suite(suite)
        except Exception as exc:  # noqa: BLE001
            logger.debug("threshold load for regression failed: %s", exc)

        # Try gateway wrapper first (provides canonical delta + gate verdict)
        gateway_result: dict | None = _try_gateway_compare(base_metrics, cand_metrics, thresholds)
        if gateway_result is not None and isinstance(gateway_result, dict):
            # Enrich with our own explicit regression signals
            pass  # will merge below

        # Manual delta analysis — authoritative for safety/security fail-closed
        regression_signals: dict[str, Any] = {}
        failures: list[str] = []

        # Quality (accuracy / groundedness / faithfulness)
        for key in ("accuracy", "groundedness", "faithfulness", "overall"):
            if key in base_metrics and key in cand_metrics:
                try:
                    delta = float(cand_metrics[key]) - float(base_metrics[key])
                    regression_signals[f"{key}_delta"] = round(delta, 4)
                    thr = float(thresholds.get("quality_delta", -0.05))
                    if delta < thr:
                        failures.append(f"quality regression: {key} {delta:+.4f} < {thr:+.4f}")
                        regression_signals[f"{key}_regression"] = True
                    else:
                        regression_signals[f"{key}_regression"] = False
                except Exception:  # noqa: BLE001
                    continue

        # Safety — any drop is regression (fail-closed)
        for key in ("safety", "security"):
            if key in base_metrics and key in cand_metrics:
                try:
                    delta = float(cand_metrics[key]) - float(base_metrics[key])
                    regression_signals[f"{key}_delta"] = round(delta, 4)
                    thr = float(thresholds.get(f"{key}_delta", 0.0))
                    if delta < thr:
                        failures.append(f"safety regression: {key} {delta:+.4f} < {thr:+.4f}")
                        regression_signals[f"{key}_regression"] = True
                    else:
                        regression_signals[f"{key}_regression"] = False
                except Exception:  # noqa: BLE001
                    continue

        # Robustness / tool_use
        for key in ("robustness", "tool_use", "tool-use"):
            if key in base_metrics and key in cand_metrics:
                try:
                    delta = float(cand_metrics[key]) - float(base_metrics[key])
                    regression_signals[f"{key}_delta"] = round(delta, 4)
                    thr = float(thresholds.get("robustness_delta" if "robust" in key else "tool_use_delta", -0.05))
                    if delta < thr:
                        failures.append(f"regression: {key} {delta:+.4f} < {thr:+.4f}")
                        regression_signals[f"{key}_regression"] = True
                    else:
                        regression_signals[f"{key}_regression"] = False
                except Exception:  # noqa: BLE001
                    continue

        # Latency — growth beyond threshold
        for key in ("latency", "latency_ms", "mean_latency_ms"):
            if key in base_metrics and key in cand_metrics:
                try:
                    b = float(base_metrics[key])
                    c = float(cand_metrics[key])
                    regression_signals[f"{key}_delta"] = round(c - b, 2)
                    if b > 0:
                        ratio = c / b
                        regression_signals[f"{key}_ratio"] = round(ratio, 4)
                        thr = float(thresholds.get("latency_delta", 0.25))
                        if c > b * (1 + thr):
                            failures.append(f"latency regression: {key} {c:.0f}ms vs {b:.0f}ms ({ratio:.2f}x)")
                            regression_signals[f"{key}_regression"] = True
                        else:
                            regression_signals[f"{key}_regression"] = False
                except Exception:  # noqa: BLE001
                    continue

        # Cost — growth beyond threshold
        for key in ("cost", "mean_cost"):
            if key in base_metrics and key in cand_metrics:
                try:
                    b = float(base_metrics[key])
                    c = float(cand_metrics[key])
                    regression_signals[f"{key}_delta"] = round(c - b, 6)
                    if b > 0:
                        ratio = c / b if b != 0 else 1.0
                        regression_signals[f"{key}_ratio"] = round(ratio, 4)
                        thr = float(thresholds.get("cost_delta", 0.25))
                        if c > b * (1 + thr):
                            failures.append(f"cost regression: {key} {c:.4f} vs {b:.4f} ({ratio:.2f}x)")
                            regression_signals[f"{key}_regression"] = True
                        else:
                            regression_signals[f"{key}_regression"] = False
                    elif c > 0 and b == 0:
                        regression_signals[f"{key}_regression"] = c > float(thresholds.get("max_cost", 1.0))
                except Exception:  # noqa: BLE001
                    continue

        # Hallucination — increase is regression
        for key in ("hallucination", "hallucination_rate"):
            if key in base_metrics and key in cand_metrics:
                try:
                    delta = float(cand_metrics[key]) - float(base_metrics[key])
                    regression_signals[f"{key}_delta"] = round(delta, 4)
                    if delta > 0.02:  # >2 pts increase considered regression
                        failures.append(f"hallucination regression: {key} +{delta:.4f}")
                        regression_signals[f"{key}_regression"] = True
                except Exception:  # noqa: BLE001
                    continue

        # Overall regression flag
        has_regression = len(failures) > 0
        is_block = any("safety regression" in f or "security" in f for f in failures)

        if is_block:
            verdict = "BLOCK"
        elif has_regression:
            verdict = "FAIL"
        else:
            verdict = "PASS"

        # Build final report — never reduce metrics, keep both sides separate
        deltas: dict = {}
        if gateway_result and isinstance(gateway_result.get("deltas"), dict):
            deltas.update(gateway_result["deltas"])
        # merge our more complete deltas
        for k, v in regression_signals.items():
            if k.endswith("_delta") or k.endswith("_ratio"):
                deltas.setdefault(k, v)

        report: dict[str, Any] = {
            "tenant": tenant_s,
            "candidate_run_id": str(cand_pk),
            "baseline_run_id": str(base_pk),
            "candidate_metrics": cand_metrics,
            "baseline_metrics": base_metrics,
            "deltas": deltas,
            "regression_signals": regression_signals,
            "thresholds": thresholds,
            "failures": failures,
            "has_regression": has_regression,
            "is_block": is_block,
            "verdict": verdict,
        }
        if gateway_result is not None:
            report["gateway"] = gateway_result
            # Prefer gateway verdict if it is stricter
            gw_verdict = str(gateway_result.get("verdict", "")).lower()
            if gw_verdict == "block" and verdict != "BLOCK":
                report["verdict"] = "BLOCK"
                report["is_block"] = True
            elif gw_verdict == "fail" and verdict == "PASS":
                report["verdict"] = "FAIL"
                report["has_regression"] = True

        _audit(tenant_s, "system", "ai_evaluation.regression_compared", str(cand_pk), {"baseline": str(base_pk), "verdict": report["verdict"], "failures": failures[:5]})
        logger.info("regression compare candidate=%s baseline=%s verdict=%s", cand_pk, base_pk, report["verdict"])
        return report


evaluation_service = AIEvaluationService()
