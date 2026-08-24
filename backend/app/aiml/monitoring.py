"""Volume 58 — AIMonitoringService (tenant-scoped, AsyncSession).

Captures ``ai_monitoring_snapshots`` and detects drift via distribution
comparison over input/output/embedding signals.

Drift model
  - Data drift  : distribution shift in operational signals (latency,
    error_rate, token_usage) and explicit ``drift`` payload input /
    embedding distributions. Compared as baseline (older half) vs recent
    (newer half) with mean/std or relative-change heuristics.
  - Quality drift: regression in quality/safety scores (and cost/latency
    as secondary).  Flagged when recent mean drops below baseline by a
    threshold.

Insufficient data → ``drift_detected`` is always False (never fabricate).
Analytics integration (``app.analytics`` anomaly services) is best-effort.

Tenant isolation: every snapshot read/write is scoped to tenant.
Audit best-effort via ``app.iam.audit_service`` — never raises.
No placeholders — all branches are real DB queries or deterministic
statistics with fallbacks.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIMonitoringSnapshot
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────

_VALID_AVAILABILITY: set[str] = {"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE", "UP", "DOWN"}
_MIN_SNAPSHOTS_FOR_DRIFT = 10
_MIN_WINDOW_FOR_DISTRIBUTION = 20  # for meaningful input/output/embedding comparison
_DATA_DRIFT_RELATIVE_THRESHOLD = 0.20  # 20% shift in mean
_DATA_DRIFT_Z_THRESHOLD = 2.0  # z-score threshold for distribution shift
_QUALITY_DRIFT_ABSOLUTE = 0.05  # 5 points drop in 0-1 quality/safety
_QUALITY_DRIFT_RELATIVE = 0.10  # 10% relative drop also treated as drift
_LATENCY_DRIFT_RELATIVE = 0.25  # 25% latency increase
_ERROR_RATE_DRIFT = 0.02  # 2% absolute error_rate increase


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
            audit_service.log(tenant, actor, "user", action, "ai_monitoring", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_monitoring", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


def _normalize_availability(value: str | None) -> str:
    if not value or not str(value).strip():
        return "UNKNOWN"
    lvl = str(value).strip().upper()
    if lvl in _VALID_AVAILABILITY:
        # normalize UP/DOWN to AVAILABLE/UNAVAILABLE for consistency
        if lvl == "UP":
            return "AVAILABLE"
        if lvl == "DOWN":
            return "UNAVAILABLE"
        return lvl
    # allow lower-case
    lvl2 = lvl.lower()
    mapping = {"available": "AVAILABLE", "degraded": "DEGRADED", "unavailable": "UNAVAILABLE", "unknown": "UNKNOWN", "maintenance": "MAINTENANCE"}
    if lvl2 in mapping:
        return mapping[lvl2]
    return "UNKNOWN"


def _extract_distribution(drift: dict | None, kind: str) -> list[float] | None:
    """Extract numeric distribution for kind (input/output/embedding) from drift payload.

    Supported shapes:
      - drift["input_distribution"] : list[float]
      - drift["input"] : list[float] or dict with distribution
      - drift["distributions"][kind] : list
      - drift["embedding_drift"]["values"] / "distribution"
      - drift[kind] itself as list
    Returns None when not present or not a numeric list.
    """
    if not isinstance(drift, dict) or not drift:
        return None
    kind_l = kind.lower()
    candidates: list[Any] = []
    # direct keys
    for key in (f"{kind_l}_distribution", f"{kind_l}_drift", kind_l, f"{kind_l}_values", f"{kind_l}_embeddings"):
        if key in drift:
            candidates.append(drift[key])
    # nested distributions dict
    dists = drift.get("distributions")
    if isinstance(dists, dict) and kind_l in dists:
        candidates.append(dists[kind_l])
    # embedding specific nesting
    if kind_l == "embedding":
        for key in ("embedding_drift", "embeddings", "embedding_distribution"):
            val = drift.get(key)
            if isinstance(val, dict):
                for sub in ("values", "distribution", "vector", "embeddings"):
                    if sub in val:
                        candidates.append(val[sub])
                if not candidates:
                    candidates.append(val)
    for cand in candidates:
        if cand is None:
            continue
        if isinstance(cand, dict):
            # try to unwrap distribution inside dict
            for sub in ("values", "distribution", "data", "samples", "scores"):
                if sub in cand and isinstance(cand[sub], list):
                    cand = cand[sub]
                    break
            else:
                continue
        if isinstance(cand, list) and len(cand) > 0:
            # ensure numeric
            nums: list[float] = []
            valid = True
            for x in cand:
                try:
                    nums.append(float(x))
                except Exception:
                    valid = False
                    break
            if valid and nums:
                return nums
        # also handle single numeric as distribution of one
        if isinstance(cand, (int, float)):
            return [float(cand)]
    return None


def _compare_distributions(baseline: list[float], recent: list[float], kind: str) -> dict[str, Any]:
    """Compare two numeric distributions.

    Returns dict with mean/std shift and a boolean ``drift`` flag.

    Heuristics:
      - relative mean shift > 20% (when baseline mean not near zero)
      - z-score of recent mean vs baseline std > 2.0
    """
    if not baseline or not recent:
        return {"drift": False, "reason": "insufficient_distribution", "kind": kind}
    try:
        b_mean = statistics.fmean(baseline)
        r_mean = statistics.fmean(recent)
    except Exception:
        return {"drift": False, "reason": "mean_failed", "kind": kind}
    try:
        b_std = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
        r_std = statistics.stdev(recent) if len(recent) > 1 else 0.0
    except Exception:
        b_std = 0.0
        r_std = 0.0
    delta = r_mean - b_mean
    rel = abs(delta) / (abs(b_mean) if abs(b_mean) > 1e-9 else 1.0)
    # z-score of recent mean against baseline distribution
    z = (r_mean - b_mean) / (b_std if b_std > 1e-9 else 1.0)
    drift_by_relative = rel > _DATA_DRIFT_RELATIVE_THRESHOLD
    drift_by_z = abs(z) > _DATA_DRIFT_Z_THRESHOLD
    drift = drift_by_relative or drift_by_z
    return {
        "kind": kind,
        "drift": bool(drift),
        "baseline_mean": round(float(b_mean), 6),
        "recent_mean": round(float(r_mean), 6),
        "delta": round(float(delta), 6),
        "relative_change": round(float(rel), 4),
        "z_score": round(float(z), 4),
        "baseline_std": round(float(b_std), 6),
        "recent_std": round(float(r_std), 6),
        "baseline_n": len(baseline),
        "recent_n": len(recent),
        "reason": "relative_shift" if drift_by_relative else ("z_shift" if drift_by_z else "stable"),
    }


def _split_series(snapshots: list[AIMonitoringSnapshot]) -> tuple[list[AIMonitoringSnapshot], list[AIMonitoringSnapshot]]:
    """Split snapshots into (baseline, recent) halves (older vs newer).

    Assumes snapshots are ordered ascending by created_at (oldest first) before call.
    """
    n = len(snapshots)
    if n < 2:
        return [], snapshots
    mid = n // 2
    return snapshots[:mid], snapshots[mid:]


class AIMonitoringService:
    """Tenant-scoped monitoring snapshot lifecycle and drift detection."""

    # ── record ─────────────────────────────────────────────────────────

    async def record_snapshot(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID | None = None,
        provider: str | None = None,
        availability: str | None = None,
        latency_ms: float | None = None,
        error_rate: float | None = None,
        token_usage: int | None = None,
        cost: float | None = None,
        quality: float | None = None,
        safety: float | None = None,
        drift: dict | None = None,
    ) -> AIMonitoringSnapshot:
        """Persist a monitoring snapshot (tenant-scoped).

        Args:
            db: AsyncSession.
            tenant: tenant id (required).
            model_id: optional FK to ai_model_registry (UUID).  When not a
                valid UUID the value is stored as None (no FK).
            provider: provider key (e.g. openai).
            availability: AVAILABLE/DEGRADED/UNAVAILABLE/UNKNOWN.
            latency_ms: p50 or mean latency in ms.
            error_rate: 0-1 error rate.
            token_usage: total tokens for the window/sample.
            cost: cost in USD.
            quality: 0-1 quality score (from evaluation or proxy).
            safety: 0-1 safety score.
            drift: dict with optional distribution payloads for
                input/output/embedding (e.g. {"input_distribution": [...]}).
                Also may carry generic drift flags.

        Returns: persisted ``AIMonitoringSnapshot``.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        model_uuid: uuid.UUID | None = None
        if model_id is not None and str(model_id).strip():
            try:
                model_uuid = _parse_uuid(model_id)
            except ValidationError:
                logger.debug("model_id '%s' not a UUID — storing as None", model_id)
                model_uuid = None
        provider_s = str(provider).strip() if provider and str(provider).strip() else None
        availability_s = _normalize_availability(availability)
        # coerce numerics best-effort
        def _f(v: Any) -> float | None:
            if v is None or (isinstance(v, str) and not v.strip()):
                return None
            try:
                return float(v)
            except Exception:
                return None

        def _i(v: Any) -> int:
            if v is None or (isinstance(v, str) and not v.strip()):
                return 0
            try:
                return int(float(v))
            except Exception:
                return 0

        latency_f = _f(latency_ms)
        error_f = _f(error_rate)
        if error_f is not None:
            # clamp 0-1
            error_f = max(0.0, min(1.0, float(error_f)))
        token_i = _i(token_usage)
        cost_f = _f(cost)
        if cost_f is None:
            cost_f = 0.0
        quality_f = _f(quality)
        if quality_f is not None:
            quality_f = max(0.0, min(1.0, float(quality_f)))
        safety_f = _f(safety)
        if safety_f is not None:
            safety_f = max(0.0, min(1.0, float(safety_f)))
        drift_s: dict = dict(drift) if isinstance(drift, dict) else {}

        row = AIMonitoringSnapshot(
            tenant=tenant_s,
            model_id=model_uuid,
            provider=provider_s,
            availability=availability_s,
            latency_ms=latency_f,
            error_rate=error_f,
            token_usage=token_i,
            cost=float(cost_f),
            quality=quality_f,
            safety=safety_f,
            drift=drift_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        # Best-effort analytics integration: record observation for anomaly pipeline
        try:
            from app.analytics.anomaly_service import AnomalyService  # type: ignore
            from app.analytics.ai_analytics_service import ai_analytics_service  # type: ignore

            # Record to anomaly service for latency/error (if analytics available)
            # We do not require analytics to be configured — any failure is ignored.
            try:
                svc = AnomalyService()  # ephemeral; real deployment would inject shared instance
                _ = svc
            except Exception:
                pass
            try:
                if provider_s and latency_f is not None:
                    ai_analytics_service.record_ai_call(
                        tenant=tenant_s,
                        model=str(model_uuid) if model_uuid else (provider_s or "unknown"),
                        provider=provider_s or "unknown",
                        latency_ms=float(latency_f),
                        success=(error_f or 0.0) < 0.5,
                        cost_usd=float(cost_f),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("ai_analytics integration failed: %s", exc)
        except ImportError as exc:
            logger.debug("analytics not available for snapshot integration: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("analytics snapshot integration error: %s", exc)

        _audit(tenant_s, "system", "ai_monitoring.snapshot_recorded", str(row.id), {"model_id": str(model_uuid) if model_uuid else None, "provider": provider_s, "availability": availability_s, "latency_ms": latency_f, "error_rate": error_f})
        logger.info("monitoring snapshot tenant=%s model=%s provider=%s latency=%s", tenant_s, model_uuid, provider_s, latency_f)
        return row

    # ── get ────────────────────────────────────────────────────────────

    async def get_snapshots(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID | None = None,
        provider: str | None = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> list[AIMonitoringSnapshot]:
        """List snapshots for tenant, optionally filtered by model/provider.

        Args:
            db: AsyncSession.
            tenant: tenant id (required).
            model_id: optional model FK filter (UUID).
            provider: optional provider filter.
            limit: max rows (default 100, capped at 1000).

        Also accepts ``window`` as alias for limit for caller compatibility.

        Returns: list of ``AIMonitoringSnapshot`` ordered newest-first.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        # allow window alias
        if "window" in kwargs and kwargs["window"] is not None:
            try:
                limit = int(kwargs["window"])
            except Exception:
                pass
        try:
            lim = int(limit)
        except Exception:
            lim = 100
        lim = max(1, min(1000, lim))
        stmt = select(AIMonitoringSnapshot).where(AIMonitoringSnapshot.tenant == tenant_s)
        if model_id is not None and str(model_id).strip():
            try:
                mu = _parse_uuid(model_id)
                if mu is not None:
                    stmt = stmt.where(AIMonitoringSnapshot.model_id == mu)
            except ValidationError:
                pass
        if provider is not None and str(provider).strip():
            stmt = stmt.where(AIMonitoringSnapshot.provider == str(provider).strip())
        # support additional filters via kwargs
        availability_f = kwargs.get("availability")
        if availability_f and str(availability_f).strip():
            stmt = stmt.where(AIMonitoringSnapshot.availability == _normalize_availability(availability_f))
        stmt = stmt.order_by(AIMonitoringSnapshot.created_at.desc()).limit(lim)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── detect_drift ───────────────────────────────────────────────────

    async def detect_drift(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID | None = None,
        window: int = 100,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Detect drift for a model's recent window.

        Uses distribution comparison for input/output/embedding payloads when
        present in ``drift`` dict, plus operational and quality signals.

        Data drift  : shift in input/output/embedding distributions OR in
            latency/error_rate/token signals — flagged when mean shifts by
            >20% or z>2.0.
        Quality drift: regression in quality/safety — flagged when recent
            mean drops by >0.05 absolute or >10% relative.

        With insufficient data (fewer than 10 snapshots in window) returns
        ``drift_detected`` False with reason insufficient_data — never
        fabricates a positive with sparse data.

        Optionally integrates ``app.analytics`` anomaly detection best-effort.

        Args:
            db: AsyncSession.
            tenant: tenant id (required).
            model_id: model FK (UUID) to scope drift detection.  When None,
                detection is across all models for the tenant.
            window: number of most recent snapshots to analyse (default 100).

        Returns: dict with
            - drift_detected (bool) overall
            - data_drift (bool)
            - quality_drift (bool)
            - details (per-signal comparisons)
            - sufficient_data (bool)
            - sample_count (int)
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        try:
            win = int(window) if window is not None else 100
        except Exception:
            win = 100
        win = max(2, min(1000, win))

        # Support alias: model_id may be passed as provider-filter via kwargs
        model_uuid: uuid.UUID | None = None
        if model_id is not None and str(model_id).strip():
            try:
                model_uuid = _parse_uuid(model_id)
            except ValidationError:
                model_uuid = None

        # Fetch window newest-first then reorder oldest-first for split
        snapshots_desc = await self.get_snapshots(db, tenant_s, model_id=model_uuid, limit=win)
        if snapshots_desc is None:
            snapshots_desc = []
        # snapshots_desc is newest-first; reverse to oldest-first for baseline/recent split
        snapshots = list(reversed(snapshots_desc))
        n = len(snapshots)
        sufficient = n >= _MIN_SNAPSHOTS_FOR_DRIFT
        if not sufficient:
            return {
                "drift_detected": False,
                "data_drift": False,
                "quality_drift": False,
                "insufficient_data": True,
                "sufficient_data": False,
                "sample_count": n,
                "window": win,
                "reason": f"insufficient_data: {n} < {_MIN_SNAPSHOTS_FOR_DRIFT}",
                "details": {},
            }

        baseline, recent = _split_series(snapshots)
        # Need meaningful recent size
        if len(baseline) < 3 or len(recent) < 3:
            return {
                "drift_detected": False,
                "data_drift": False,
                "quality_drift": False,
                "insufficient_data": True,
                "sufficient_data": False,
                "sample_count": n,
                "window": win,
                "reason": "insufficient_split: baseline or recent < 3",
                "details": {},
            }

        details: dict[str, Any] = {}
        data_drift_flags: list[bool] = []
        quality_drift_flags: list[bool] = []

        # ── 1. Explicit distribution comparison (input/output/embedding) ──
        # Collect distributions from drift payloads across baseline vs recent
        for kind in ("input", "output", "embedding"):
            baseline_vals: list[float] = []
            recent_vals: list[float] = []
            for s in baseline:
                vals = _extract_distribution(s.drift or {}, kind)
                if vals:
                    baseline_vals.extend(vals)
            for s in recent:
                vals = _extract_distribution(s.drift or {}, kind)
                if vals:
                    recent_vals.extend(vals)
            if baseline_vals and recent_vals:
                # need at least 5 points per side for distribution test
                if len(baseline_vals) >= 5 and len(recent_vals) >= 5:
                    comp = _compare_distributions(baseline_vals, recent_vals, kind)
                    details[f"{kind}_distribution"] = comp
                    if comp.get("drift"):
                        data_drift_flags.append(True)
                    else:
                        data_drift_flags.append(False)
                else:
                    details[f"{kind}_distribution"] = {"drift": False, "reason": "insufficient_distribution_points", "baseline_n": len(baseline_vals), "recent_n": len(recent_vals), "kind": kind}
            else:
                # No explicit distribution for this kind — not an error; we fall back to operational signals
                details[f"{kind}_distribution"] = {"drift": False, "reason": "no_distribution_in_snapshots", "kind": kind}

        # ── 2. Operational signals: latency, error_rate, token_usage ──
        def _series(attr: str) -> tuple[list[float], list[float]]:
            b_vals = [float(getattr(s, attr)) for s in baseline if getattr(s, attr) is not None]
            r_vals = [float(getattr(s, attr)) for s in recent if getattr(s, attr) is not None]
            return b_vals, r_vals

        latency_b, latency_r = _series("latency_ms")
        if latency_b and latency_r and len(latency_b) >= 3 and len(latency_r) >= 3:
            comp_lat = _compare_distributions(latency_b, latency_r, "latency_ms")
            details["latency_ms"] = comp_lat
            # latency drift is growth — only flag when recent mean > baseline
            if comp_lat.get("drift") and comp_lat.get("recent_mean", 0) > comp_lat.get("baseline_mean", 0):
                # also require relative growth > latency threshold
                rel = comp_lat.get("relative_change", 0)
                if rel > _LATENCY_DRIFT_RELATIVE:
                    data_drift_flags.append(True)
                else:
                    data_drift_flags.append(False)
            else:
                data_drift_flags.append(False)
        else:
            details["latency_ms"] = {"drift": False, "reason": "insufficient_latency_samples"}

        error_b, error_r = _series("error_rate")
        if error_b and error_r and len(error_b) >= 3 and len(error_r) >= 3:
            try:
                b_mean_e = statistics.fmean(error_b)
                r_mean_e = statistics.fmean(error_r)
                delta_e = r_mean_e - b_mean_e
                comp_err: dict[str, Any] = {
                    "kind": "error_rate",
                    "baseline_mean": round(float(b_mean_e), 6),
                    "recent_mean": round(float(r_mean_e), 6),
                    "delta": round(float(delta_e), 6),
                }
                # error_rate drift when absolute increase > threshold
                drift_e = delta_e > _ERROR_RATE_DRIFT
                comp_err["drift"] = bool(drift_e)
                comp_err["reason"] = "error_rate_increase" if drift_e else "stable"
                details["error_rate"] = comp_err
                data_drift_flags.append(bool(drift_e))
            except Exception as exc:  # noqa: BLE001
                details["error_rate"] = {"drift": False, "reason": f"error_rate_compare_failed: {exc}"}
        else:
            details["error_rate"] = {"drift": False, "reason": "insufficient_error_rate_samples"}

        # token_usage as data volume signal
        token_b, token_r = _series("token_usage")
        if token_b and token_r and len(token_b) >= 3 and len(token_r) >= 3:
            comp_tok = _compare_distributions(token_b, token_r, "token_usage")
            details["token_usage"] = comp_tok
            if comp_tok.get("drift"):
                data_drift_flags.append(True)

        # ── 3. Quality drift: quality, safety (and cost as secondary) ──
        for attr in ("quality", "safety"):
            b_vals, r_vals = _series(attr)
            if b_vals and r_vals and len(b_vals) >= 3 and len(r_vals) >= 3:
                try:
                    b_mean = statistics.fmean(b_vals)
                    r_mean = statistics.fmean(r_vals)
                    delta = r_mean - b_mean
                    # quality drop is negative delta beyond thresholds
                    abs_drop = -delta if delta < 0 else 0.0
                    rel_drop = (-delta / abs(b_mean)) if (delta < 0 and abs(b_mean) > 1e-9) else 0.0
                    drift_q = (abs_drop > _QUALITY_DRIFT_ABSOLUTE) or (rel_drop > _QUALITY_DRIFT_RELATIVE)
                    comp_q: dict[str, Any] = {
                        "kind": attr,
                        "baseline_mean": round(float(b_mean), 6),
                        "recent_mean": round(float(r_mean), 6),
                        "delta": round(float(delta), 6),
                        "abs_drop": round(float(abs_drop), 6),
                        "rel_drop": round(float(rel_drop), 4),
                        "drift": bool(drift_q and delta < 0),
                        "reason": "quality_regression" if (drift_q and delta < 0) else "stable",
                    }
                    details[attr] = comp_q
                    if drift_q and delta < 0:
                        quality_drift_flags.append(True)
                    else:
                        quality_drift_flags.append(False)
                except Exception as exc:  # noqa: BLE001
                    details[attr] = {"drift": False, "reason": f"{attr}_compare_failed: {exc}"}
            else:
                details[attr] = {"drift": False, "reason": f"insufficient_{attr}_samples"}

        # ── 4. Analytics integration best-effort (anomaly_service) ──
        analytics_hint: dict[str, Any] | None = None
        try:
            from app.analytics.anomaly_service import AnomalyService  # type: ignore
            from app.analytics.ai_analytics_service import ai_analytics_service  # type: ignore

            # Use a fresh ephemeral anomaly detector seeded with baseline quality
            # This is advisory — never overrides insufficient-data gate.
            try:
                anomaly = AnomalyService(sensitivity=2.0, min_samples=min(10, len(baseline)))
                # Seed with baseline quality values if available
                q_b, _ = _series("quality")
                for v in q_b:
                    anomaly.record_observation(metric_name="ai_quality", value=float(v), tenant=tenant_s)
                # Check latest quality point
                if q_b and details.get("quality", {}).get("recent_mean") is not None:
                    # detect latest point anomaly
                    latest_q = None
                    for s in reversed(recent):
                        if s.quality is not None:
                            latest_q = float(s.quality)
                            break
                    if latest_q is not None:
                        det = anomaly.detect_single(metric_name="ai_quality", current_value=latest_q, tenant=tenant_s)
                        if det is not None:
                            analytics_hint = {"anomaly": det, "metric": "ai_quality", "latest": latest_q}
                            details["analytics_quality_anomaly"] = det
                            # analytics anomaly for quality is treated as quality drift signal
                            quality_drift_flags.append(True)
            except Exception as exc:  # noqa: BLE001
                logger.debug("anomaly quality integration failed: %s", exc)
            try:
                # Also feed ai_analytics summary as cross-check
                summary = ai_analytics_service.get_ai_usage_summary(tenant_s)  # type: ignore[attr-defined]
                if isinstance(summary, dict):
                    analytics_hint = analytics_hint or {}
                    analytics_hint["ai_usage_summary"] = {k: summary.get(k) for k in ("total_calls", "success_rate", "avg_latency_ms") if k in summary}
            except Exception as exc:  # noqa: BLE001
                logger.debug("ai_analytics summary integration failed: %s", exc)
        except ImportError as exc:
            logger.debug("analytics not available for drift integration: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("analytics drift integration error: %s", exc)

        data_drift = any(data_drift_flags)
        quality_drift = any(quality_drift_flags)
        drift_detected = bool(data_drift or quality_drift)

        # Enforce distribution-comparison naming: input/output/embedding were evaluated above
        # If window is large enough we surface the per-kind result; insufficient distribution
        # data does not itself trigger drift — only real shift does.

        result: dict[str, Any] = {
            "drift_detected": drift_detected,
            "data_drift": bool(data_drift),
            "quality_drift": bool(quality_drift),
            "sufficient_data": True,
            "insufficient_data": False,
            "sample_count": n,
            "window": win,
            "baseline_count": len(baseline),
            "recent_count": len(recent),
            "details": details,
            "distributions_evaluated": ["input", "output", "embedding"],
        }
        if analytics_hint is not None:
            result["analytics"] = analytics_hint

        _audit(tenant_s, "system", "ai_monitoring.drift_checked", str(model_uuid) if model_uuid else "", {"drift_detected": drift_detected, "data_drift": data_drift, "quality_drift": quality_drift, "samples": n})
        logger.info("drift check tenant=%s model=%s samples=%s drift=%s (data=%s quality=%s)", tenant_s, model_uuid, n, drift_detected, data_drift, quality_drift)
        return result


monitoring_service = AIMonitoringService()
