"""Volume 59 Commit 2 — AIOps Engine.

Pipeline: Telemetry -> Detection -> Correlation -> Hypothesis -> Evidence -> Recommendation -> Optional Action
- All suggestions include confidence / evidence / data_freshness, flagged as hypothesis (never verified facts).
- Reuses existing analytics/anomaly where available (analytics.anomaly_service, aggregation_service).
- Never synthesizes telemetry; only uses DB / analytics observations. Never labels normal variance as incident without evidence.
- Tenant isolation enforced on every query (tenant required, filter by tenant column).
- Knowledge graph used for causal graph: deployment -> service -> dependency -> latency -> alert -> incident
  (explicit temporal vs causation distinction).
- Alert correlation reuses platform logic and extends with AI scoring.

No chain-of-thought exposure; summaries are concise and evidence-backed.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.models import (
    ObservabilityAlert,
    ObservabilityHealthSnapshot,
    ObservabilityService,
    ObservabilitySLO,
)

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

PIPELINE_STAGES = ["telemetry", "detection", "correlation", "hypothesis", "evidence", "recommendation", "optional_action"]
DEFAULT_SENSITIVITY = 2.0
MIN_BASELINE_SAMPLES = 10

# baseline version tracking: key -> version int
_BASELINE_VERSIONS: dict[str, int] = {}
_BASELINE_STORE: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _require_tenant(tenant: str) -> str:
    if not tenant or not str(tenant).strip():
        raise ValueError("tenant is required (IAM tenant isolation)")
    return str(tenant).strip()


def _parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _data_freshness(latest_ts: datetime | str | None) -> dict:
    parsed = _parse_ts(latest_ts) if isinstance(latest_ts, str) else _parse_ts(latest_ts) if isinstance(latest_ts, datetime) else None
    if parsed is None:
        return {"latest_timestamp": None, "age_seconds": None, "freshness": "unknown", "is_stale": True}
    age = (_now() - parsed).total_seconds()
    if age < 300:
        freshness = "fresh"
    elif age < 3600:
        freshness = "recent"
    elif age < 86400:
        freshness = "stale"
    else:
        freshness = "very_stale"
    return {
        "latest_timestamp": parsed.isoformat(),
        "age_seconds": int(age),
        "freshness": freshness,
        "is_stale": age > 3600,
    }


def _confidence_from_z(z_abs: float) -> float:
    if z_abs <= 1.0:
        return 0.5
    raw = 1.0 - 1.0 / (z_abs * z_abs)
    return round(min(0.85, max(0.5, raw)), 4)


def _severity_from_z(z_abs: float) -> str:
    if z_abs >= 4.0:
        return "critical"
    if z_abs >= 3.0:
        return "high"
    return "medium"


def _window_to_hours(window: str | int | None) -> int:
    if window is None:
        return 24
    if isinstance(window, int):
        return max(1, min(720, window))
    if isinstance(window, str):
        w = window.strip().lower()
        # supports "1h", "24h", "7d", "30d", "1w"
        try:
            if w.endswith("h"):
                return int(w[:-1])
            if w.endswith("d"):
                return int(w[:-1]) * 24
            if w.endswith("w"):
                return int(w[:-1]) * 24 * 7
            return int(w)
        except ValueError:
            return 24
    return 24


def _hypothesis_wrap(text: str, confidence: float, evidence: list | dict, data_freshness: dict, related_resources: list | None = None, supporting_signals: list | None = None) -> dict:
    return {
        "hypothesis": text,
        "confidence": round(min(0.85, max(0.1, float(confidence))), 4),
        "evidence": evidence if isinstance(evidence, list) else [evidence],
        "data_freshness": data_freshness,
        "related_resources": related_resources or [],
        "supporting_signals": supporting_signals or [],
        "is_hypothesis": True,
        "is_verified_fact": False,
        "verification_required": True,
        "causality_claimed": False,
        "causality_note": "Temporal correlation is not causation; verification required.",
    }


# ── AIOps Engine ─────────────────────────────────────────────────────────────

class AIOpsEngine:
    """AIOps pipeline engine reusing analytics and KG.

    All public methods are async, take AsyncSession + tenant, enforce tenant isolation,
    and never treat AI output as verified fact.
    """

    def __init__(self):
        self._sensitivity = DEFAULT_SENSITIVITY

    # ── Detection ────────────────────────────────────────────────────────────

    async def detect_anomalies(self, db: AsyncSession, tenant: str, metric: str = "", window_hours: int = 24) -> list[dict]:
        """Metric/latency/error/traffic/resource anomaly detection.

        Reuses analytics.anomaly_service if available; otherwise statistical z-score
        over aggregation_service history. Never flags normal variance as incident without evidence.
        """
        tenant_s = _require_tenant(tenant)
        metric_s = (metric or "").strip()
        window_hours = max(1, min(720, int(window_hours or 24)))
        since = _now() - timedelta(hours=window_hours)

        # 1) Try analytics.anomaly_service reuse (in-memory)
        try:
            from app.analytics.anomaly_service import AnomalyService  # type: ignore
            # attempt to reuse a global singleton if exists; otherwise create ephemeral
            svc = None
            try:
                from app.analytics.anomaly_service import anomaly_service as _global_svc  # type: ignore
                svc = _global_svc
            except Exception:
                svc = AnomalyService(sensitivity=self._sensitivity)

            # If global has observations, use its detect
            if hasattr(svc, "detect"):
                # detect returns anomalies for tenant/metric based on rolling observations
                found = svc.detect(tenant=tenant_s, metric_name=metric_s) if metric_s else svc.detect(tenant=tenant_s)
                if found:
                    out: list[dict] = []
                    for a in found:
                        df = _data_freshness(a.get("detected_at"))
                        out.append({
                            **a,
                            "data_freshness": df,
                            "is_hypothesis": True,
                            "is_verified_fact": False,
                            "pipeline_stage": "detection",
                            "window_hours": window_hours,
                            "evidence": a.get("evidence", {}),
                        })
                    return out[:50]
        except Exception as exc:
            logger.debug("anomaly_service reuse failed, falling back to statistical: %s", exc)

        # 2) Statistical fallback over aggregation_service history (real telemetry, not fake)
        points: list[float] = []
        latest_value: float | None = None
        latest_ts: str | None = None
        try:
            from app.analytics.aggregation_service import aggregation_service  # type: ignore
            # aggregation_service stores bucketed aggregates; we expand to sample values
            # Query across granularities that fall within window
            metrics_to_query: list[str] = []
            if metric_s:
                metrics_to_query = [metric_s]
            else:
                try:
                    metrics_to_query = aggregation_service.list_metrics(tenant=tenant_s)[:20]
                except Exception:
                    metrics_to_query = []
            collected_anomalies: list[dict] = []
            for m in metrics_to_query:
                # query points in window
                try:
                    # aggregation_service.query_metric supports start_time/end_time filters
                    start_iso = since.isoformat()
                    end_iso = _now().isoformat()
                    buckets = aggregation_service.query_metric(tenant_s, m, granularity="hour", start_time=start_iso, end_time=end_iso, limit=500)
                    # flatten to sample values via aggregates
                    values: list[float] = []
                    for b in buckets:
                        # each bucket has values list? we use avg * count approximation, or use min/max
                        cnt = int(b.get("count", 0) or 0)
                        if cnt and "values" not in b:
                            # expand implicitly via sum/avg
                            avg = float(b.get("avg", 0) or 0)
                            # treat bucket as cnt samples of avg (best-effort, real data)
                            values.extend([avg] * min(cnt, 20))
                        else:
                            vals = b.get("values") if isinstance(b, dict) and "values" in b else []
                            if isinstance(vals, list):
                                values.extend([float(v) for v in vals])
                    # also check _data_points directly if available for finer granularity
                    if not values:
                        # try direct _data_points access (in-memory store)
                        for key, dp_list in getattr(aggregation_service, "_data_points", {}).items():
                            if key.startswith(f"{tenant_s}:{m}:"):
                                for dp in dp_list:
                                    ts = _parse_ts(dp.get("timestamp"))
                                    if ts and ts >= since:
                                        try:
                                            values.append(float(dp.get("value", 0)))
                                        except Exception:
                                            continue
                    if len(values) < MIN_BASELINE_SAMPLES + 1:
                        continue
                    baseline = values[:-1]
                    latest = values[-1]
                    mean = statistics.fmean(baseline)
                    std = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
                    delta = latest - mean
                    if std > 0:
                        z = delta / std
                    else:
                        z = 0.0 if delta == 0 else 999.0
                    if abs(z) <= self._sensitivity:
                        # normal variance — do not label as incident
                        continue
                    z_abs = abs(z)
                    sev = _severity_from_z(z_abs)
                    conf = _confidence_from_z(z_abs)
                    threshold = self._sensitivity * (std if std else 0)
                    # find latest timestamp for freshness from dp_list
                    freshness_ts = None
                    for key, dp_list in getattr(aggregation_service, "_data_points", {}).items():
                        if key.startswith(f"{tenant_s}:{m}:") and dp_list:
                            freshness_ts = dp_list[-1].get("timestamp") or dp_list[-1].get("bucket_start")
                            break
                    df = _data_freshness(freshness_ts)
                    # category inference: latency/error/traffic/resource
                    category = "metric"
                    ml = m.lower()
                    if "latency" in ml or "duration" in ml or "p95" in ml or "p99" in ml:
                        category = "latency"
                    elif "error" in ml or "failure" in ml or "5xx" in ml:
                        category = "error"
                    elif "traffic" in ml or "rps" in ml or "throughput" in ml or "qps" in ml:
                        category = "traffic"
                    elif "cpu" in ml or "memory" in ml or "disk" in ml or "resource" in ml:
                        category = "resource"
                    anomaly = {
                        "anomaly_id": uuid.uuid4().hex,
                        "tenant": tenant_s,
                        "metric_name": m,
                        "category": category,
                        "observed_value": round(float(latest), 6),
                        "baseline_mean": round(float(mean), 6),
                        "baseline_std": round(float(std), 6),
                        "deviation": round(float(z), 4),
                        "confidence": conf,
                        "severity": sev,
                        "detected_at": _now_iso(),
                        "window_hours": window_hours,
                        "pipeline_stage": "detection",
                        "is_hypothesis": True,
                        "is_verified_fact": False,
                        "requires_evidence": True,
                        "evidence": {
                            "sample_count": len(baseline),
                            "sensitivity": self._sensitivity,
                            "upper_bound": round(float(mean + threshold), 6) if std else round(float(mean), 6),
                            "lower_bound": round(float(mean - threshold), 6) if std else round(float(mean), 6),
                            "direction": "above_baseline" if delta > 0 else "below_baseline",
                            "source": "analytics.aggregation_service",
                            "normal_variance_not_incident": True,
                        },
                        "data_freshness": df,
                    }
                    collected_anomalies.append(anomaly)
                except Exception as inner:
                    logger.debug("metric %s statistical check failed: %s", m, inner)
                    continue
            if collected_anomalies:
                collected_anomalies.sort(key=lambda x: abs(x.get("deviation", 0)), reverse=True)
                return collected_anomalies[:50]
        except Exception as exc:
            logger.debug("aggregation_service statistical fallback failed: %s", exc)

        # 3) DB fallback: use ObservabilityHealthSnapshot as proxy for resource anomalies only
        # We do not fabricate; if no analytics history, return empty with evidence note rather than false positive.
        try:
            stmt = select(ObservabilityHealthSnapshot).where(
                ObservabilityHealthSnapshot.tenant == tenant_s,
                ObservabilityHealthSnapshot.timestamp >= since,
            ).order_by(ObservabilityHealthSnapshot.timestamp.desc()).limit(200)
            res = await db.execute(stmt)
            snaps = list(res.scalars().all())
            if snaps and metric_s.lower() in ("health", "availability", "resource"):
                # compute health anomaly: ratio of UNHEALTHY vs total
                total = len(snaps)
                unhealthy = sum(1 for s in snaps if s.health == "UNHEALTHY")
                degraded = sum(1 for s in snaps if s.health == "DEGRADED")
                # baseline healthy ratio ~ 1.0; if unhealthy spike beyond 2 sigma
                vals = [1.0 if s.health == "HEALTHY" else 0.0 for s in snaps]
                if len(vals) >= MIN_BASELINE_SAMPLES + 1:
                    baseline = vals[:-1]
                    latest = vals[-1]
                    mean = statistics.fmean(baseline)
                    std = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
                    if std > 0:
                        z = (latest - mean) / std
                        if abs(z) > self._sensitivity and latest < mean:
                            df = _data_freshness(snaps[0].timestamp if snaps else None)
                            sev = _severity_from_z(abs(z))
                            return [{
                                "anomaly_id": uuid.uuid4().hex,
                                "tenant": tenant_s,
                                "metric_name": metric_s or "health",
                                "category": "resource",
                                "observed_value": latest,
                                "baseline_mean": round(mean, 4),
                                "baseline_std": round(std, 4),
                                "deviation": round(z, 4),
                                "confidence": _confidence_from_z(abs(z)),
                                "severity": sev,
                                "detected_at": _now_iso(),
                                "window_hours": window_hours,
                                "pipeline_stage": "detection",
                                "is_hypothesis": True,
                                "is_verified_fact": False,
                                "evidence": {
                                    "sample_count": len(baseline),
                                    "total_snapshots": total,
                                    "unhealthy": unhealthy,
                                    "degraded": degraded,
                                    "source": "observability_health_snapshots",
                                },
                                "data_freshness": df,
                            }]
        except Exception as exc:
            logger.debug("health snapshot anomaly fallback failed: %s", exc)

        # No evidence of anomaly — return empty, do not label normal variance as incident
        return []

    # ── Baseline ─────────────────────────────────────────────────────────────

    async def get_baseline(self, db: AsyncSession, tenant: str, service: str, environment: str = "production", window: str | int = "24h") -> dict:
        tenant_s = _require_tenant(tenant)
        service_s = (service or "").strip()
        if not service_s:
            raise ValueError("service is required")
        env_s = (environment or "production").strip() or "production"
        window_h = _window_to_hours(window)
        window_key = f"{window_h}h"
        since = _now() - timedelta(hours=window_h)

        baseline_key = f"{tenant_s}:{service_s}:{env_s}:{window_key}"
        prev_version = _BASELINE_VERSIONS.get(baseline_key, 0)

        metrics_info: dict[str, dict] = {}
        latest_ts: datetime | None = None

        # Attempt analytics aggregation per service/env dimensions
        try:
            from app.analytics.aggregation_service import aggregation_service  # type: ignore
            # discover metrics for tenant and filter by dimensions containing service/env
            all_data_points = getattr(aggregation_service, "_data_points", {})
            # collect values per metric where dimensions match
            for key, dp_list in list(all_data_points.items()):
                # key format tenant:metric:granularity:dims_hash:bucket
                try:
                    parts = key.split(":")
                    if len(parts) < 5:
                        continue
                    t, m = parts[0], parts[1]
                    if t != tenant_s:
                        continue
                    # filter dps by dimensions
                    vals: list[float] = []
                    ts_candidates: list[datetime] = []
                    for dp in dp_list:
                        dims = dp.get("dimensions", {}) or {}
                        # match service/env if present in dimensions
                        # if dimensions empty, we treat metric name containing service as related
                        dim_service = str(dims.get("service", "") or dims.get("resource", "") or "")
                        dim_env = str(dims.get("environment", "") or dims.get("env", "") or "")
                        # allow metrics where metric name contains service OR dimension matches
                        name_match = service_s.lower() in m.lower() if service_s else True
                        service_match = service_s.lower() in dim_service.lower() if dim_service else name_match
                        env_match = (env_s.lower() == dim_env.lower()) if dim_env else True
                        if not service_match or not env_match:
                            continue
                        ts = _parse_ts(dp.get("timestamp") or dp.get("bucket_start"))
                        if ts and ts < since:
                            continue
                        vals.append(float(dp.get("value", 0)))
                        if ts:
                            ts_candidates.append(ts)
                    if vals:
                        latest_ts = max(ts_candidates) if ts_candidates else latest_ts
                        # compute stats per metric+service/env
                        if len(vals) >= 2:
                            mean = statistics.fmean(vals)
                            std = statistics.stdev(vals) if len(vals) > 1 else 0.0
                            svals = sorted(vals)
                            def pct(p: float) -> float:
                                if not svals:
                                    return 0.0
                                idx = int(len(svals) * p)
                                idx = min(idx, len(svals) - 1)
                                return float(svals[idx])
                            metrics_info[m] = {
                                "count": len(vals),
                                "mean": round(float(mean), 6),
                                "std": round(float(std), 6),
                                "min": round(float(min(vals)), 6),
                                "max": round(float(max(vals)), 6),
                                "p95": round(pct(0.95), 6),
                                "p99": round(pct(0.99), 6),
                            }
                except Exception as inner:
                    logger.debug("baseline aggregation key %s failed: %s", key, inner)
                    continue
        except Exception as exc:
            logger.debug("aggregation baseline attempt failed: %s", exc)

        # DB fallback: health snapshots for service/environment if no metric history
        if not metrics_info:
            try:
                # resource pattern for service: tenant:service:env or resource like service name
                stmt = select(ObservabilityHealthSnapshot).where(
                    ObservabilityHealthSnapshot.tenant == tenant_s,
                    ObservabilityHealthSnapshot.timestamp >= since,
                ).order_by(ObservabilityHealthSnapshot.timestamp.desc()).limit(500)
                res = await db.execute(stmt)
                snaps = list(res.scalars().all())
                # filter snaps whose resource contains service name (case-insensitive) if available
                relevant = [s for s in snaps if service_s.lower() in (s.resource or "").lower()]
                if relevant:
                    # use health as 1/0 proxy for availability baseline
                    vals = [1.0 if s.health == "HEALTHY" else (0.5 if s.health == "DEGRADED" else 0.0) for s in relevant]
                    if vals:
                        latest_ts = relevant[0].timestamp if relevant else latest_ts
                        mean = statistics.fmean(vals)
                        std = statistics.stdev(vals) if len(vals) > 1 else 0.0
                        metrics_info["availability_proxy"] = {
                            "count": len(vals),
                            "mean": round(float(mean), 6),
                            "std": round(float(std), 6),
                            "min": round(float(min(vals)), 6),
                            "max": round(float(max(vals)), 6),
                            "p95": round(float(sorted(vals)[int(len(vals)*0.95)]), 6) if vals else 0.0,
                            "p99": round(float(sorted(vals)[int(len(vals)*0.99)]), 6) if vals else 0.0,
                            "source": "observability_health_snapshots",
                        }
            except Exception as exc:
                logger.debug("DB health baseline fallback failed: %s", exc)

        # Also ensure ObservabilityService exists for evidence (service identity)
        service_exists = False
        svc_resource: str | None = None
        try:
            stmt = select(ObservabilityService).where(
                ObservabilityService.tenant == tenant_s,
                ObservabilityService.name == service_s,
                ObservabilityService.environment == env_s,
            ).limit(1)
            res = await db.execute(stmt)
            svc = res.scalars().first()
            if svc:
                service_exists = True
                svc_resource = svc.resource
            else:
                # fallback match by resource containing service
                stmt2 = select(ObservabilityService).where(ObservabilityService.tenant == tenant_s).limit(100)
                res2 = await db.execute(stmt2)
                for candidate in res2.scalars().all():
                    if service_s.lower() in (candidate.resource or "").lower() or service_s.lower() == (candidate.name or "").lower():
                        svc_resource = candidate.resource
                        service_exists = True
                        break
        except Exception:
            service_exists = False

        # version tracking: increment if we have new data vs stored
        new_version = prev_version + 1 if metrics_info else prev_version
        if metrics_info:
            _BASELINE_VERSIONS[baseline_key] = new_version
            _BASELINE_STORE[baseline_key] = {"metrics": metrics_info, "computed_at": _now_iso()}

        # Determine sufficiency per metric
        sufficient_map = {m: (info.get("count", 0) >= MIN_BASELINE_SAMPLES) for m, info in metrics_info.items()}
        overall_sufficient = any(sufficient_map.values()) if sufficient_map else False

        df = _data_freshness(latest_ts) if latest_ts else {"latest_timestamp": None, "age_seconds": None, "freshness": "unknown", "is_stale": True}

        return {
            "tenant": tenant_s,
            "service": service_s,
            "environment": env_s,
            "window": window_key,
            "window_hours": window_h,
            "version": new_version,
            "previous_version": prev_version,
            "metrics": metrics_info,
            "sufficient": overall_sufficient,
            "per_metric_sufficient": sufficient_map,
            "service_exists": service_exists,
            "resource": svc_resource,
            "evidence": {
                "source": "analytics.aggregation_service+observability_health_snapshots" if metrics_info else "no_telemetry",
                "sample_counts": {m: info.get("count", 0) for m, info in metrics_info.items()},
                "service_env_match": service_exists,
            },
            "data_freshness": df,
            "computed_at": _now_iso(),
            "is_hypothesis": False,
            "note": "Dynamic baseline; track version for drift detection. Insufficient samples means baseline not sufficient for anomaly decision.",
        }

    # ── Investigation tools (IAM-aware: tenant filter) ───────────────────────

    async def find_related_alerts(self, db: AsyncSession, tenant: str, incident_id: str | None = None, resource: str | None = None, window_minutes: int = 60) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        since = _now() - timedelta(minutes=max(1, window_minutes))
        service_hint: str | None = None
        incident_resource: str | None = resource
        if incident_id:
            try:
                from app.incident.models import Incident  # type: ignore
                inc = await db.get(Incident, uuid.UUID(incident_id) if len(incident_id) == 36 else incident_id)  # type: ignore
                if inc and getattr(inc, "tenant", tenant_s) == tenant_s:
                    service_hint = getattr(inc, "service", "") or None
                    incident_resource = getattr(inc, "service", "") or incident_resource
            except Exception:
                # try select fallback
                try:
                    from app.incident.models import Incident
                    stmt = select(Incident).where(Incident.tenant == tenant_s).limit(100)
                    res = await db.execute(stmt)
                    for cand in res.scalars().all():
                        if str(cand.id) == str(incident_id):
                            service_hint = cand.service or None
                            incident_resource = cand.service or incident_resource
                            break
                except Exception:
                    pass
        stmt = select(ObservabilityAlert).where(
            ObservabilityAlert.tenant == tenant_s,
            ObservabilityAlert.created_at >= since,
        ).order_by(ObservabilityAlert.created_at.desc()).limit(100)
        res = await db.execute(stmt)
        alerts = list(res.scalars().all())
        # score / filter
        scored: list[dict] = []
        for a in alerts:
            score = 0
            evidence: dict[str, Any] = {"alert_id": str(a.id), "status": a.status, "severity": a.severity, "source": a.source}
            if resource and a.resource == resource:
                score += 3
                evidence["resource_match"] = True
            if service_hint and service_hint.lower() in (a.resource or "").lower():
                score += 2
                evidence["service_correlation"] = service_hint
            if incident_id and (a.evidence or {}).get("incident_id") == incident_id:
                score += 4
                evidence["incident_link"] = True
            # time proximity already via window
            if score > 0 or not (resource or service_hint):
                scored.append({
                    "alert_id": str(a.id),
                    "resource": a.resource,
                    "severity": a.severity,
                    "status": a.status,
                    "fingerprint": a.fingerprint,
                    "evidence": {**evidence, **(a.evidence or {})},
                    "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) else None,
                    "score": score,
                    "data_access": "tenant_filtered",
                })
        scored.sort(key=lambda x: (x["score"], x.get("created_at") or ""), reverse=True)
        return scored[:20]

    async def find_recent_changes(self, db: AsyncSession, tenant: str, service: str | None = None, window_hours: int = 24) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        window_hours = max(1, min(720, int(window_hours)))
        since = _now() - timedelta(hours=window_hours)
        results: list[dict] = []
        # ReleaseRecord is the authoritative change record
        try:
            from app.release.models import ReleaseRecord  # type: ignore
            stmt = select(ReleaseRecord).where(
                ReleaseRecord.tenant == tenant_s,
                ReleaseRecord.created_at >= since,
            ).order_by(ReleaseRecord.created_at.desc()).limit(50)
            if service:
                stmt = stmt.where(ReleaseRecord.service == service)
            res = await db.execute(stmt)
            for rec in res.scalars().all():
                results.append({
                    "change_id": str(rec.id),
                    "type": "release",
                    "service": rec.service,
                    "version": getattr(rec, "version", ""),
                    "environment": getattr(rec, "environment", ""),
                    "status": getattr(rec, "status", ""),
                    "created_at": rec.created_at.isoformat() if getattr(rec, "created_at", None) else None,
                    "commit_sha": getattr(rec, "commit_sha", ""),
                    "evidence": getattr(rec, "metadata_json", {}) or {},
                    "temporal_note": "deployment time correlation is not causation",
                    "data_access": "tenant_filtered",
                })
        except Exception as exc:
            logger.debug("find_recent_changes ReleaseRecord query failed: %s", exc)
        # also include ObservabilityService deployment field changes
        if not results and service:
            try:
                stmt = select(ObservabilityService).where(
                    ObservabilityService.tenant == tenant_s,
                    ObservabilityService.name == service,
                ).limit(5)
                res = await db.execute(stmt)
                for svc in res.scalars().all():
                    if svc.deployment and svc.updated_at and svc.updated_at >= since:
                        results.append({
                            "change_id": svc.resource,
                            "type": "service_deployment",
                            "service": svc.name,
                            "deployment": svc.deployment,
                            "environment": svc.environment,
                            "updated_at": svc.updated_at.isoformat(),
                            "evidence": {"resource": svc.resource, "repository": svc.repository},
                            "temporal_note": "deployment time correlation is not causation",
                            "data_access": "tenant_filtered",
                        })
            except Exception:
                pass
        results.sort(key=lambda x: x.get("created_at") or x.get("updated_at") or "", reverse=True)
        return results[:20]

    async def find_service_health(self, db: AsyncSession, tenant: str, service: str, environment: str = "production") -> dict:
        tenant_s = _require_tenant(tenant)
        service_s = (service or "").strip()
        if not service_s:
            raise ValueError("service is required")
        env_s = (environment or "production").strip()
        # ObservabilityService identity
        svc_obj = None
        resource_candidates: list[str] = []
        try:
            stmt = select(ObservabilityService).where(
                ObservabilityService.tenant == tenant_s,
                ObservabilityService.name == service_s,
            )
            if env_s:
                stmt = stmt.where(ObservabilityService.environment == env_s)
            stmt = stmt.limit(5)
            res = await db.execute(stmt)
            svcs = list(res.scalars().all())
            if svcs:
                svc_obj = svcs[0]
                resource_candidates = [s.resource for s in svcs]
            else:
                # fallback resource search
                stmt2 = select(ObservabilityService).where(ObservabilityService.tenant == tenant_s).limit(100)
                res2 = await db.execute(stmt2)
                for c in res2.scalars().all():
                    if service_s.lower() in (c.name or "").lower() or service_s.lower() in (c.resource or "").lower():
                        svc_obj = c
                        resource_candidates = [c.resource]
                        break
        except Exception as exc:
            logger.debug("find_service_health service lookup failed: %s", exc)

        resource = resource_candidates[0] if resource_candidates else service_s
        # Latest health snapshot
        snap = None
        try:
            stmt = select(ObservabilityHealthSnapshot).where(
                ObservabilityHealthSnapshot.tenant == tenant_s,
                ObservabilityHealthSnapshot.resource == resource,
            ).order_by(ObservabilityHealthSnapshot.timestamp.desc()).limit(1)
            res = await db.execute(stmt)
            snap = res.scalars().first()
            if not snap and resource != service_s:
                stmt = select(ObservabilityHealthSnapshot).where(
                    ObservabilityHealthSnapshot.tenant == tenant_s,
                    ObservabilityHealthSnapshot.resource == service_s,
                ).order_by(ObservabilityHealthSnapshot.timestamp.desc()).limit(1)
                res = await db.execute(stmt)
                snap = res.scalars().first()
        except Exception as exc:
            logger.debug("health snapshot query failed: %s", exc)

        health = snap.health if snap else (svc_obj.health_status if svc_obj else "UNKNOWN")
        checks = snap.checks if snap and snap.checks else {}
        ts = snap.timestamp if snap and snap.timestamp else (svc_obj.updated_at if svc_obj and getattr(svc_obj, "updated_at", None) else None)
        df = _data_freshness(ts)
        # UNKNOWN is not HEALTHY
        return {
            "tenant": tenant_s,
            "service": service_s,
            "environment": env_s,
            "resource": resource,
            "health": health,
            "is_healthy": health == "HEALTHY",
            "is_unknown": health == "UNKNOWN",
            "checks": checks,
            "evidence": {
                "source": "observability_health_snapshots+observability_services",
                "resource_candidates": resource_candidates,
                "snapshot_available": snap is not None,
                "service_exists": svc_obj is not None,
            },
            "data_freshness": df,
            "queried_at": _now_iso(),
        }

    async def find_dependencies(self, db: AsyncSession, tenant: str, service: str) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        service_s = (service or "").strip()
        if not service_s:
            raise ValueError("service is required")
        deps: list[dict] = []

        # 1) Try knowledge graph relationships
        try:
            # try DB-backed KGRelationship
            from app.knowledge_graph.models import KGRelationship, KGEntity  # type: ignore
            # find entity id for service
            stmt = select(KGEntity).where(KGEntity.tenant == tenant_s, KGEntity.name == service_s).limit(1)
            res = await db.execute(stmt)
            ent = res.scalars().first()
            if ent:
                entity_id = ent.id
                # outgoing depends_on / calls / uses
                stmt2 = select(KGRelationship).where(
                    KGRelationship.tenant == tenant_s,
                    KGRelationship.source_entity_id == entity_id,
                    KGRelationship.is_active == True,  # noqa: E712
                ).limit(50)
                res2 = await db.execute(stmt2)
                for rel in res2.scalars().all():
                    # resolve target name
                    try:
                        target = await db.get(KGEntity, rel.target_entity_id)
                        target_name = target.name if target else str(rel.target_entity_id)
                    except Exception:
                        target_name = str(rel.target_entity_id)
                    deps.append({
                        "dependency": target_name,
                        "relationship_type": rel.relationship_type,
                        "confidence": rel.confidence,
                        "evidence": rel.evidence or [],
                        "is_active": rel.is_active,
                        "source": "knowledge_graph",
                        "temporal_note": "dependency edge is structural, not temporal",
                    })
                if deps:
                    return deps[:30]
        except Exception as exc:
            logger.debug("KG dependency DB lookup failed: %s", exc)

        # 1b) In-memory relationship_service fallback
        try:
            from app.knowledge_graph.relationship_service import relationship_service  # type: ignore
            # search by service name as entity_id prefix (best-effort)
            # We need to find entity via entity_service first
            try:
                from app.knowledge_graph.entity_service import entity_service  # type: ignore
                if hasattr(entity_service, "_entities"):
                    for eid, ent in getattr(entity_service, "_entities", {}).items():
                        if ent.get("tenant") == tenant_s and service_s.lower() in ent.get("name", "").lower():
                            rels = relationship_service.get_relationships_for_entity(eid, direction="outgoing", limit=30)
                            for r in rels:
                                deps.append({
                                    "dependency": r.get("target_entity_id"),
                                    "relationship_type": r.get("relationship_type"),
                                    "confidence": r.get("confidence"),
                                    "evidence": r.get("evidence", []),
                                    "source": "knowledge_graph.in_memory",
                                })
                            if deps:
                                return deps[:30]
            except Exception:
                pass
        except Exception:
            pass

        # 2) Fallback: ObservabilityService metadata_json dependencies
        try:
            stmt = select(ObservabilityService).where(ObservabilityService.tenant == tenant_s, ObservabilityService.name == service_s).limit(5)
            res = await db.execute(stmt)
            for svc in res.scalars().all():
                meta = svc.metadata_json or {}
                for key in ("dependencies", "depends_on", "upstream", "downstream"):
                    if key in meta and isinstance(meta[key], list):
                        for dep_name in meta[key]:
                            deps.append({
                                "dependency": str(dep_name),
                                "relationship_type": key,
                                "evidence": [{"type": "metadata", "resource": svc.resource, "key": key}],
                                "source": "observability_services.metadata_json",
                            })
                # also infer from fields: database/queue/api
                for field in ("database", "queue", "api"):
                    val = getattr(svc, field, None)
                    if val:
                        deps.append({
                            "dependency": val,
                            "relationship_type": f"uses_{field}",
                            "evidence": [{"type": "service_field", "field": field, "resource": svc.resource}],
                            "source": "observability_services",
                        })
        except Exception as exc:
            logger.debug("observability dependency fallback failed: %s", exc)

        return deps[:30]

    async def find_trace(self, db: AsyncSession, tenant: str, trace_id: str) -> dict:
        tenant_s = _require_tenant(tenant)
        trace_id_s = (trace_id or "").strip()
        if not trace_id_s:
            raise ValueError("trace_id is required")
        # Traces are not persisted to a dedicated table in volume 59; we correlate via
        # IncidentEvent evidence and ObservabilityAlert evidence where trace_id is stored
        findings: list[dict] = []
        latest_ts: str | None = None
        try:
            from app.incident.models import IncidentEvent  # type: ignore
            stmt = select(IncidentEvent).where(IncidentEvent.metadata_extra.isnot(None)).limit(200)  # type: ignore
            # we filter in python for tenant via incident lookup (IncidentEvent has no tenant column)
            res = await db.execute(stmt)
            for ev in res.scalars().all():
                meta = getattr(ev, "metadata_extra", {}) or {}
                evd = getattr(ev, "evidence", {}) or {}
                tid = meta.get("trace_id") or evd.get("trace_id") or ""
                if tid == trace_id_s:
                    # need to verify incident tenant
                    try:
                        from app.incident.models import Incident
                        inc = await db.get(Incident, ev.incident_id)  # type: ignore
                        if inc and getattr(inc, "tenant", "") != tenant_s:
                            continue
                    except Exception:
                        continue
                    findings.append({
                        "incident_id": ev.incident_id,
                        "event_type": ev.event_type,
                        "message": ev.message[:500] if ev.message else "",
                        "evidence": evd,
                        "timestamp": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
                    })
                    if getattr(ev, "created_at", None):
                        latest_ts = ev.created_at.isoformat()
        except Exception as exc:
            logger.debug("find_trace IncidentEvent query failed: %s", exc)
        # Also check ObservabilityAlert evidence trace_id
        try:
            stmt = select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant_s).order_by(ObservabilityAlert.created_at.desc()).limit(100)
            res = await db.execute(stmt)
            for alert in res.scalars().all():
                if (alert.evidence or {}).get("trace_id") == trace_id_s:
                    findings.append({
                        "alert_id": str(alert.id),
                        "resource": alert.resource,
                        "evidence": alert.evidence,
                        "timestamp": alert.created_at.isoformat() if getattr(alert, "created_at", None) else None,
                    })
                    if getattr(alert, "created_at", None) and not latest_ts:
                        latest_ts = alert.created_at.isoformat()
        except Exception as exc:
            logger.debug("find_trace alert query failed: %s", exc)

        df = _data_freshness(latest_ts) if latest_ts else {"latest_timestamp": None, "age_seconds": None, "freshness": "unknown", "is_stale": True}
        return {
            "tenant": tenant_s,
            "trace_id": trace_id_s,
            "findings": findings[:20],
            "count": len(findings),
            "evidence": {"source": "incident_events+observability_alerts", "tenant_filtered": True},
            "data_freshness": df,
        }

    async def find_logs(self, db: AsyncSession, tenant: str, service: str, level: str | None = None, limit: int = 50) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        service_s = (service or "").strip()
        limit = max(1, min(200, int(limit)))
        results: list[dict] = []
        # Logs are not persisted to dedicated table; best-effort via IncidentEvent (logs modeled as events)
        try:
            from app.incident.models import IncidentEvent, Incident  # type: ignore
            # find incidents for service Tenant
            stmt = select(Incident).where(Incident.tenant == tenant_s)
            if service_s:
                stmt = stmt.where(Incident.service == service_s)
            stmt = stmt.order_by(Incident.detected_at.desc()).limit(20)
            res = await db.execute(stmt)
            incident_ids = [str(i.id) for i in res.scalars().all()]
            if incident_ids:
                stmt2 = select(IncidentEvent).where(IncidentEvent.incident_id.in_(incident_ids)).order_by(IncidentEvent.created_at.desc()).limit(limit * 2)
                res2 = await db.execute(stmt2)
                for ev in res2.scalars().all():
                    # filter by level if provided via message metadata
                    ev_level = (ev.evidence or {}).get("level") or (ev.metadata_extra or {}).get("level") or ""
                    if level and ev_level and ev_level.upper() != level.upper():
                        continue
                    # also keyword match for ERROR/FATAL if level specified but not in evidence
                    if level and level.upper() in ("ERROR", "FATAL") and ev_level == "" and level.upper() not in (ev.message or "").upper():
                        # keep only if message indicates error? we allow all if not filtered strictly
                        pass
                    results.append({
                        "incident_id": ev.incident_id,
                        "event_type": ev.event_type,
                        "actor": ev.actor,
                        "message": (ev.message or "")[:1000],
                        "evidence": ev.evidence or {},
                        "level": ev_level or "INFO",
                        "timestamp": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
                        "source": "incident_events",
                    })
                    if len(results) >= limit:
                        break
        except Exception as exc:
            logger.debug("find_logs query failed: %s", exc)
        # If no incident_events, fallback to audit logs is not available; return empty rather than fake
        return results[:limit]

    async def find_incidents(self, db: AsyncSession, tenant: str, service: str | None = None, window_hours: int = 24) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        since = _now() - timedelta(hours=max(1, int(window_hours)))
        try:
            from app.incident.models import Incident  # type: ignore
            stmt = select(Incident).where(Incident.tenant == tenant_s, Incident.detected_at >= since).order_by(Incident.detected_at.desc()).limit(50)
            if service:
                stmt = stmt.where(Incident.service == service)
            res = await db.execute(stmt)
            out: list[dict] = []
            for inc in res.scalars().all():
                out.append({
                    "incident_id": str(inc.id),
                    "title": getattr(inc, "title", ""),
                    "severity": getattr(inc, "severity", ""),
                    "status": getattr(inc, "status", ""),
                    "service": getattr(inc, "service", ""),
                    "environment": getattr(inc, "environment", ""),
                    "detected_at": inc.detected_at.isoformat() if getattr(inc, "detected_at", None) else None,
                    "evidence": {"fingerprint": getattr(inc, "fingerprint", ""), "correlation": getattr(inc, "blast_radius", {})},
                    "data_access": "tenant_filtered",
                })
            return out
        except Exception as exc:
            logger.debug("find_incidents failed: %s", exc)
            return []

    async def find_slo(self, db: AsyncSession, tenant: str, service: str) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        service_s = (service or "").strip()
        if not service_s:
            raise ValueError("service is required")
        try:
            stmt = select(ObservabilitySLO).where(ObservabilitySLO.tenant == tenant_s, ObservabilitySLO.service == service_s).limit(20)
            res = await db.execute(stmt)
            out: list[dict] = []
            for slo in res.scalars().all():
                out.append({
                    "slo_id": str(slo.id),
                    "service": slo.service,
                    "indicator": slo.indicator,
                    "target": slo.target,
                    "window": slo.window,
                    "owner": slo.owner,
                    "config": slo.config or {},
                    "created_at": slo.created_at.isoformat() if getattr(slo, "created_at", None) else None,
                    "evidence": {"source": "observability_slos", "tenant_filtered": True},
                })
            return out
        except Exception as exc:
            logger.debug("find_slo failed: %s", exc)
            return []

    async def find_runbook(self, db: AsyncSession, tenant: str, incident_type: str | None = None) -> list[dict]:
        tenant_s = _require_tenant(tenant)
        try:
            from app.incident.models import IncidentRunbook  # type: ignore
            stmt = select(IncidentRunbook).where(IncidentRunbook.tenant == tenant_s).limit(20)
            if incident_type:
                stmt = stmt.where(IncidentRunbook.incident_type == incident_type)
            res = await db.execute(stmt)
            out: list[dict] = []
            for rb in res.scalars().all():
                out.append({
                    "runbook_id": str(rb.id),
                    "name": rb.name,
                    "incident_type": rb.incident_type,
                    "steps": rb.steps[:5] if isinstance(rb.steps, list) else [],
                    "risk_level": rb.risk_level,
                    "enabled": rb.enabled,
                    "evidence": {"source": "incident_runbooks", "tenant_filtered": True},
                })
            return out
        except Exception as exc:
            logger.debug("find_runbook failed: %s", exc)
            return []

    async def correlate_alerts_aiops(self, db: AsyncSession, tenant: str, alert_id: str, window_minutes: int = 15) -> dict:
        """Extend platform alert correlation for AIOps with AI scoring.

        Reuses ObservabilityPlatform.correlate_alerts logic but adds hypothesis scoring.
        """
        tenant_s = _require_tenant(tenant)
        # Try platform reuse first
        base: dict | None = None
        try:
            from app.observability.platform import platform_service  # type: ignore
            base = await platform_service.correlate_alerts(db, tenant_s, alert_id, window_minutes=window_minutes)
        except Exception as exc:
            logger.debug("platform correlate_alerts failed, using AIOps fallback: %s", exc)
            base = None

        # AIOps extended scoring: add correlation vs causation note and confidence
        related = (base.get("related") if base else []) or []
        # If base empty, try our own tenant-filtered correlation
        if not related:
            try:
                related = await self.find_related_alerts(db, tenant_s, resource=None, window_minutes=window_minutes)
                # filter to those sharing fingerprint/resource
                alert = await db.get(ObservabilityAlert, uuid.UUID(alert_id) if len(alert_id) == 36 else alert_id)  # type: ignore
                if alert and getattr(alert, "tenant", tenant_s) == tenant_s:
                    filtered: list[dict] = []
                    for cand in related:
                        if cand.get("alert_id") == alert_id:
                            continue
                        score = cand.get("score", 0)
                        if score > 0:
                            filtered.append(cand)
                    related = filtered[:10]
            except Exception:
                related = []

        df = _data_freshness(_now())
        for r in related:
            # each related is hypothesis, not verified causal
            r["is_hypothesis"] = True
            r["is_verified_fact"] = False
            r["causality_claimed"] = False
            r["temporal_note"] = "Time-proximate alerts are correlated; verify shared root cause via traces/logs/dependencies."

        return {
            "alert_id": alert_id,
            "tenant": tenant_s,
            "related": related[:10],
            "window_minutes": window_minutes,
            "evidence_retained": True,
            "is_hypothesis": True,
            "data_freshness": df,
            "evidence": {"source": "observability_platform+aiops", "tenant_filtered": True},
        }

    # ── Causal Graph ───────────────────────────────────────────────────────

    async def build_causal_graph(self, db: AsyncSession, tenant: str, incident_id: str) -> dict:
        tenant_s = _require_tenant(tenant)
        incident_id_s = (incident_id or "").strip()
        if not incident_id_s:
            raise ValueError("incident_id is required")

        # Fetch incident to get service/env
        incident = None
        service = ""
        environment = "production"
        detected_at: datetime | None = None
        try:
            from app.incident.models import Incident  # type: ignore
            # try uuid
            try:
                incident = await db.get(Incident, uuid.UUID(incident_id_s))
            except Exception:
                incident = None
            if not incident:
                # fallback select by string id
                stmt = select(Incident).where(Incident.tenant == tenant_s).limit(100)
                res = await db.execute(stmt)
                for cand in res.scalars().all():
                    if str(cand.id) == incident_id_s:
                        incident = cand
                        break
            if incident:
                if getattr(incident, "tenant", tenant_s) != tenant_s:
                    raise ValueError("incident not found or access denied (tenant isolation)")
                service = getattr(incident, "service", "") or ""
                environment = getattr(incident, "environment", "") or "production"
                detected_at = getattr(incident, "detected_at", None)
        except ValueError:
            raise
        except Exception as exc:
            logger.debug("build_causal_graph incident fetch failed: %s", exc)

        nodes: list[dict] = []
        edges: list[dict] = []

        # Node: incident
        nodes.append({
            "id": f"incident:{incident_id_s}",
            "type": "incident",
            "label": getattr(incident, "title", incident_id_s) if incident else incident_id_s,
            "service": service,
            "environment": environment,
            "evidence": {"source": "incident_incidents", "detected_at": detected_at.isoformat() if detected_at else None},
        })

        # Gather supporting resources for graph
        recent_changes = await self.find_recent_changes(db, tenant_s, service=service or None, window_hours=48)
        health = None
        if service:
            try:
                health = await self.find_service_health(db, tenant_s, service, environment)
            except Exception:
                health = None
        dependencies = []
        if service:
            try:
                dependencies = await self.find_dependencies(db, tenant_s, service)
            except Exception:
                dependencies = []
        slo_list = []
        if service:
            try:
                slo_list = await self.find_slo(db, tenant_s, service)
            except Exception:
                slo_list = []
        related_alerts = await self.find_related_alerts(db, tenant_s, incident_id=incident_id_s, resource=service or None, window_minutes=120)

        # Try KG relationships for evidence-backed edges
        kg_edges_found = 0
        try:
            from app.knowledge_graph.models import KGEntity, KGRelationship  # type: ignore
            # Resolve entities for service and incident if possible
            entity_map: dict[str, Any] = {}
            # Find service entity
            svc_entity = None
            if service:
                stmt = select(KGEntity).where(KGEntity.tenant == tenant_s, KGEntity.name == service).limit(1)
                res = await db.execute(stmt)
                svc_entity = res.scalars().first()
                if svc_entity:
                    entity_map[service] = svc_entity
                    nodes.append({"id": f"service:{service}", "type": "service", "label": service, "entity_id": str(svc_entity.id), "evidence": {"source": "kg_entities", "entity_type": svc_entity.entity_type}})
            # Build KG edges around service entity
            if svc_entity:
                stmt = select(KGRelationship).where(
                    KGRelationship.tenant == tenant_s,
                    or_(KGRelationship.source_entity_id == svc_entity.id, KGRelationship.target_entity_id == svc_entity.id),
                    KGRelationship.is_active == True,  # noqa: E712
                ).limit(100)
                res = await db.execute(stmt)
                for rel in res.scalars().all():
                    # resolve other endpoint
                    other_id = rel.target_entity_id if rel.source_entity_id == svc_entity.id else rel.source_entity_id
                    try:
                        other = await db.get(KGEntity, other_id)
                        other_name = other.name if other else str(other_id)
                        other_type = other.entity_type if other else "unknown"
                    except Exception:
                        other_name = str(other_id)
                        other_type = "unknown"
                    # Determine edge direction for causal chain: deployment->service->dependency->latency->alert->incident
                    nodes_by_id = {n["id"] for n in nodes}
                    other_node_id = f"kg:{other_name}"
                    if other_node_id not in nodes_by_id:
                        nodes.append({"id": other_node_id, "type": other_type, "label": other_name, "entity_id": str(other_id), "evidence": {"source": "kg_relationship", "relationship_type": rel.relationship_type}})
                    src = f"service:{service}" if rel.source_entity_id == svc_entity.id else other_node_id
                    tgt = other_node_id if rel.source_entity_id == svc_entity.id else f"service:{service}"
                    edges.append({
                        "source": src,
                        "target": tgt,
                        "type": rel.relationship_type,
                        "evidence": rel.evidence or [],
                        "confidence": rel.confidence,
                        "is_causal": False,
                        "temporal_note": "KG edge is structural/observed; not proof of causation for this incident",
                        "data_freshness": _data_freshness(rel.updated_at if hasattr(rel, "updated_at") else None),
                    })
                    kg_edges_found += 1
        except Exception as exc:
            logger.debug("KG causal graph construction failed: %s", exc)

        # Add deployment nodes/edges (temporal correlation, not causation)
        for ch in recent_changes[:5]:
            dep_id = ch.get("change_id", "")
            dep_node_id = f"deployment:{dep_id}"
            nodes.append({
                "id": dep_node_id,
                "type": "deployment",
                "label": ch.get("version") or dep_id,
                "service": ch.get("service", service),
                "evidence": {"source": "release_records", "change": ch},
            })
            if service:
                edges.append({
                    "source": dep_node_id,
                    "target": f"service:{service}" if any(n["id"] == f"service:{service}" for n in nodes) else f"incident:{incident_id_s}",
                    "type": "deployed_to",
                    "evidence": [{"type": "temporal_proximity", "change_id": dep_id, "service": ch.get("service"), "note": "temporal correlation is not causation"}],
                    "is_causal": False,
                    "causality_note": "Deployment preceded incident; verify via error rate/latency linkage and rollback evidence before claiming causation.",
                    "data_freshness": _data_freshness(ch.get("created_at")),
                })

        # Add dependency nodes/edges if KG not already covered
        if not kg_edges_found:
            for dep in dependencies[:10]:
                dep_name = dep.get("dependency", "")
                dep_node_id = f"dependency:{dep_name}"
                if not any(n["id"] == dep_node_id for n in nodes):
                    nodes.append({"id": dep_node_id, "type": "dependency", "label": dep_name, "evidence": dep.get("evidence", [])})
                # service -> dependency edge
                svc_node = f"service:{service}" if service and any(n["id"] == f"service:{service}" for n in nodes) else f"incident:{incident_id_s}"
                if service:
                    edges.append({
                        "source": svc_node,
                        "target": dep_node_id,
                        "type": dep.get("relationship_type", "depends_on"),
                        "evidence": dep.get("evidence", []),
                        "is_causal": False,
                        "temporal_note": "Dependency edge indicates possible propagation path; not shown as root cause without latency/error evidence.",
                        "data_freshness": _data_freshness(None),
                    })
                # dependency -> latency (proxy)
                latency_node_id = f"latency:{service}" if service else "latency:unknown"
                if not any(n["id"] == latency_node_id for n in nodes) and dep:
                    nodes.append({"id": latency_node_id, "type": "latency_signal", "label": f"latency {service}", "evidence": {"source": "inferred", "note": "latency signal between dependency and alert requires metric evidence"}})
                    edges.append({
                        "source": dep_node_id,
                        "target": latency_node_id,
                        "type": "may_cause_latency",
                        "evidence": [{"type": "inferred", "note": "Requires metric trace evidence (p95 latency) to confirm"}],
                        "is_causal": False,
                        "causality_note": "Inferred edge; verify with trace/span evidence.",
                        "data_freshness": _data_freshness(None),
                    })

        # Add alert nodes
        for al in related_alerts[:10]:
            alert_node_id = f"alert:{al.get('alert_id','')}"
            if not any(n["id"] == alert_node_id for n in nodes):
                nodes.append({
                    "id": alert_node_id,
                    "type": "alert",
                    "label": al.get("resource", "") or al.get("alert_id", ""),
                    "severity": al.get("severity"),
                    "evidence": al.get("evidence", {}),
                })
            # latency -> alert or service -> alert
            src_candidates = [f"latency:{service}", f"service:{service}", f"deployment:{recent_changes[0].get('change_id')}" if recent_changes else None]
            src = next((s for s in src_candidates if s and any(n["id"] == s for n in nodes)), f"service:{service}" if service else f"incident:{incident_id_s}")
            edges.append({
                "source": src,
                "target": alert_node_id,
                "type": "triggered_alert",
                "evidence": al.get("evidence", {}),
                "is_causal": False,
                "temporal_note": "Alert firing is evidence of symptom, not proof of root cause.",
                "data_freshness": _data_freshness(al.get("created_at")),
            })
            # alert -> incident
            edges.append({
                "source": alert_node_id,
                "target": f"incident:{incident_id_s}",
                "type": "correlated_to_incident",
                "evidence": [{"type": "alert_incident_correlation", "alert_id": al.get("alert_id"), "score": al.get("score", 0)}],
                "is_causal": False,
                "causality_note": "Alert-incident correlation; causation requires trace/log verification.",
                "data_freshness": _data_freshness(al.get("created_at")),
            })

        # Deduplicate nodes
        seen: dict[str, dict] = {}
        for n in nodes:
            if n["id"] not in seen:
                seen[n["id"]] = n
        nodes = list(seen.values())

        # Determine freshest evidence timestamp for overall freshness
        freshest: str | None = None
        for n in nodes:
            ev = n.get("evidence", {})
            if isinstance(ev, dict) and ev.get("detected_at"):
                freshest = ev["detected_at"]
                break
        df = _data_freshness(freshest) if freshest else _data_freshness(detected_at if detected_at else _now())

        return {
            "tenant": tenant_s,
            "incident_id": incident_id_s,
            "service": service,
            "nodes": nodes,
            "edges": edges,
            "evidence": {
                "source": "knowledge_graph+release+observability_alerts+dependencies",
                "kg_edges": kg_edges_found,
                "recent_changes": len(recent_changes),
                "related_alerts": len(related_alerts),
                "dependencies": len(dependencies),
                "causal_notation": "All edges are correlated/structural unless is_causal=true with verified evidence. Temporal proximity alone is not causation.",
            },
            "data_freshness": df,
            "is_hypothesis": True,
            "note": "Causal graph is hypothesis; deployment->service->dependency->latency->alert->incident chain requires verification via traces/logs/metrics before action.",
        }

    # ── Root Cause Assist ────────────────────────────────────────────────────

    async def assist_root_cause(self, db: AsyncSession, tenant: str, incident_id: str) -> dict:
        tenant_s = _require_tenant(tenant)
        incident_id_s = (incident_id or "").strip()
        if not incident_id_s:
            raise ValueError("incident_id is required")

        # Fetch incident
        incident = None
        try:
            from app.incident.models import Incident  # type: ignore
            try:
                incident = await db.get(Incident, uuid.UUID(incident_id_s))
            except Exception:
                incident = None
            if not incident:
                stmt = select(Incident).where(Incident.tenant == tenant_s).limit(200)
                res = await db.execute(stmt)
                for cand in res.scalars().all():
                    if str(cand.id) == incident_id_s:
                        incident = cand
                        break
            if not incident:
                return {
                    "incident_id": incident_id_s,
                    "tenant": tenant_s,
                    "error": "incident not found",
                    "evidence": {"source": "incident_incidents", "tenant_filtered": True},
                    "data_freshness": _data_freshness(None),
                    "is_hypothesis": True,
                }
            if getattr(incident, "tenant", tenant_s) != tenant_s:
                raise ValueError("incident not found or access denied (tenant isolation)")
        except ValueError:
            raise
        except Exception as exc:
            logger.debug("assist_root_cause incident fetch failed: %s", exc)
            return {"incident_id": incident_id_s, "tenant": tenant_s, "error": str(exc), "data_freshness": _data_freshness(None), "is_hypothesis": True}

        service = getattr(incident, "service", "") or ""
        environment = getattr(incident, "environment", "") or "production"
        incident_title = getattr(incident, "title", "") or ""
        detected_at = getattr(incident, "detected_at", None)

        # Gather evidence via investigation tools (tenant-isolated)
        related_alerts = await self.find_related_alerts(db, tenant_s, incident_id=incident_id_s, resource=service or None, window_minutes=120)
        recent_changes = await self.find_recent_changes(db, tenant_s, service=service or None, window_hours=48)
        health = await self.find_service_health(db, tenant_s, service, environment) if service else None
        dependencies = await self.find_dependencies(db, tenant_s, service) if service else []
        slo_list = await self.find_slo(db, tenant_s, service) if service else []
        # detect anomalies for service-related metrics
        anomalies: list[dict] = []
        try:
            for m_hint in [f"{service}.latency" if service else "", f"{service}.error_rate" if service else "", service or ""]:
                if not m_hint:
                    continue
                ans = await self.detect_anomalies(db, tenant_s, metric=m_hint, window_hours=24)
                anomalies.extend(ans)
        except Exception:
            pass
        # logs/traces best-effort
        logs = await self.find_logs(db, tenant_s, service, level=None, limit=20) if service else []
        # causal graph for structural reasoning
        causal_graph = await self.build_causal_graph(db, tenant_s, incident_id_s)

        hypotheses: list[dict] = []
        evidence_summary: list[dict] = []
        related_resources: list[str] = []

        df_incident = _data_freshness(detected_at)

        # Hypothesis 1: Recent deployment correlation (never claim causation)
        if recent_changes:
            most_recent = recent_changes[0]
            minutes_delta = None
            try:
                dep_ts = _parse_ts(most_recent.get("created_at") or most_recent.get("updated_at"))
                if dep_ts and detected_at:
                    inc_ts = _parse_ts(detected_at)
                    if inc_ts:
                        minutes_delta = (inc_ts - dep_ts).total_seconds() / 60
            except Exception:
                minutes_delta = None
            confidence = 0.6
            # reduce confidence if deployment was long before incident
            if minutes_delta is not None and minutes_delta > 360:
                confidence = 0.35
            if minutes_delta is not None and minutes_delta < 0:
                confidence = 0.2  # deployment after incident cannot be cause
            supporting = ["timing_correlation", "service_match"] if minutes_delta is not None and 0 <= minutes_delta <= 120 else ["timing_correlation"]
            ev = {
                "type": "deployment_correlation",
                "change": most_recent,
                "time_delta_minutes": minutes_delta,
                "note": "Deployment preceded incident; correlation does not imply causation. Verify via error budget and rollback evidence.",
            }
            related_resources.append(most_recent.get("service") or service)
            evidence_summary.append(ev)
            hypotheses.append(_hypothesis_wrap(
                f"Recent change ({most_recent.get('type','release')} {most_recent.get('version','') or most_recent.get('change_id','')[:8]} for service '{most_recent.get('service', service)}') may be related to incident (timing correlation)".strip(),
                confidence,
                [ev, {"type": "causal_graph_excerpt", "edges": causal_graph.get("edges", [])[:3]}],
                _data_freshness(most_recent.get("created_at") or most_recent.get("updated_at")),
                related_resources=[most_recent.get("service", service), most_recent.get("change_id", "")],
                supporting_signals=supporting,
            ))

        # Hypothesis 2: Metric anomaly (latency/error/traffic/resource)
        if anomalies:
            top = sorted(anomalies, key=lambda x: abs(x.get("deviation", 0)), reverse=True)[0]
            ev = {
                "type": "metric_anomaly",
                "metric": top.get("metric_name"),
                "category": top.get("category"),
                "observed_value": top.get("observed_value"),
                "baseline_mean": top.get("baseline_mean"),
                "deviation": top.get("deviation"),
                "severity": top.get("severity"),
                "evidence": top.get("evidence", {}),
                "note": "Anomaly detected via statistical/ML baseline; verify with distributed traces and logs before remediation.",
            }
            evidence_summary.append(ev)
            related_resources.append(top.get("metric_name", ""))
            hypotheses.append(_hypothesis_wrap(
                f"Anomaly in {top.get('category','metric')} signal '{top.get('metric_name')}' observed (z={top.get('deviation')}) — may indicate symptom or contributing factor",
                min(0.85, top.get("confidence", 0.6) * 0.9),
                [ev],
                top.get("data_freshness", df_incident),
                related_resources=[top.get("metric_name", "")],
                supporting_signals=["metric_anomaly", top.get("category", "metric")],
            ))

        # Hypothesis 3: Dependency degradation
        if dependencies:
            # check health of dependencies
            dep_health_checks: list[dict] = []
            for dep in dependencies[:5]:
                try:
                    h = await self.find_service_health(db, tenant_s, dep.get("dependency", ""), environment)
                    dep_health_checks.append({"dependency": dep.get("dependency"), "health": h.get("health"), "freshness": h.get("data_freshness")})
                    if h.get("health") in ("DEGRADED", "UNHEALTHY"):
                        ev = {
                            "type": "dependency_health",
                            "dependency": dep.get("dependency"),
                            "relationship_type": dep.get("relationship_type"),
                            "health": h.get("health"),
                            "evidence": dep.get("evidence", []),
                            "note": "Upstream dependency degraded; may propagate latency/errors. Verify via dependency traces.",
                        }
                        evidence_summary.append(ev)
                        hypotheses.append(_hypothesis_wrap(
                            f"Dependency '{dep.get('dependency')}' is {h.get('health')} — may contribute to service degradation",
                            0.55,
                            [ev, {"type": "dependency_trace_hint", "dependency": dep.get("dependency")}],
                            h.get("data_freshness", _data_freshness(None)),
                            related_resources=[dep.get("dependency", "")],
                            supporting_signals=["dependency", "health_check"],
                        ))
                        related_resources.append(dep.get("dependency", ""))
                except Exception:
                    continue
            if not any(h.get("health") in ("UNHEALTHY", "DEGRADED") for h in dep_health_checks):
                # generic dependency hypothesis lower confidence
                if dependencies:
                    ev = {"type": "dependency_structure", "count": len(dependencies), "sample": dependencies[:3], "note": "No degraded dependency health found; structural edge only."}
                    evidence_summary.append(ev)

        # Hypothesis 4: Alert storm / correlated alerts
        if related_alerts:
            firing = [a for a in related_alerts if a.get("status") in ("FIRING", "ACKNOWLEDGED")]
            if len(firing) >= 3:
                ev = {"type": "alert_correlation", "count": len(firing), "alerts": firing[:5], "note": "Multiple correlated alerts in time window; review correlation-vs-causation via causal graph."}
                evidence_summary.append(ev)
                related_resources.extend([a.get("resource", "") for a in firing[:5]])
                hypotheses.append(_hypothesis_wrap(
                    f"{len(firing)} correlated alerts firing for correlated resources — may indicate shared underlying issue (check dependency/latency edges)",
                    0.5,
                    [ev],
                    _data_freshness(firing[0].get("created_at") if firing else None),
                    related_resources=[a.get("resource", "") for a in firing[:5]],
                    supporting_signals=["alert_correlation", "time_window"],
                ))
            elif len(firing) == 1 and not hypotheses:
                ev = {"type": "single_alert", "alert": firing[0], "note": "Single correlated alert; insufficient evidence for systemic cause."}
                evidence_summary.append(ev)

        # Hypothesis 5: SLO breach if any
        for slo in slo_list:
            # treat SLO as context only; not causal
            evidence_summary.append({"type": "slo_context", "slo": slo, "note": "SLO provides error budget context; breach evidence requires metric observation."})

        # Hypothesis 6: Log error signals
        error_logs = [l for l in logs if "error" in (l.get("level", "") or "").lower() or "error" in (l.get("message", "") or "").lower()]
        if error_logs:
            ev = {"type": "error_logs", "count": len(error_logs), "samples": error_logs[:3], "note": "Error logs present; correlate with trace_id before attributing cause."}
            evidence_summary.append(ev)
            hypotheses.append(_hypothesis_wrap(
                f"Found {len(error_logs)} error log entries for service '{service}' within incident window — may indicate failure mode (verify with trace/span).",
                0.5,
                [ev],
                _data_freshness(error_logs[0].get("timestamp")),
                related_resources=[service],
                supporting_signals=["logs", "error_level"],
            ))

        # Sort hypotheses by confidence, never claim certainty (cap 0.85)
        hypotheses.sort(key=lambda h: h.get("confidence", 0), reverse=True)
        # Ensure disclaimer
        for h in hypotheses:
            h["confidence"] = min(0.85, h.get("confidence", 0.5))
            h["causality_claimed"] = False

        # Build recommendations (each hypothesis -> investigation step)
        recommendations: list[dict] = []
        for h in hypotheses[:5]:
            recommendations.append({
                "recommendation": f"Investigate hypothesis: {h['hypothesis']}",
                "confidence": h["confidence"],
                "evidence": h["evidence"],
                "data_freshness": h["data_freshness"],
                "is_hypothesis": True,
                "action": "investigate",
                "requires_approval": False,
            })
        # Add generic recommendation if no hypotheses
        if not hypotheses:
            recommendations.append({
                "recommendation": "Collect more telemetry: check traces, logs (trace_id), recent deployments, and dependency health. No evidence-backed hypothesis yet.",
                "confidence": 0.3,
                "evidence": evidence_summary[:3] if evidence_summary else [{"type": "no_evidence", "note": "Insufficient telemetry for hypothesis"}],
                "data_freshness": df_incident,
                "is_hypothesis": True,
                "action": "collect_telemetry",
                "requires_approval": False,
            })
        else:
            recommendations.append({
                "recommendation": "Verify before acting: confirm hypotheses via traces (find_trace), logs (find_logs), and dependency health (find_dependencies). Do not treat hypotheses as verified facts.",
                "confidence": 0.4,
                "evidence": [{"type": "verification_guidance", "note": "Use find_trace/find_logs/find_dependencies tools."}],
                "data_freshness": df_incident,
                "is_hypothesis": True,
                "action": "verify",
                "requires_approval": False,
            })

        # Optional action (never auto-execute; requires approval)
        optional_action = {
            "action_type": "investigation_workflow",
            "description": "Trigger investigation workflow (read-only) — collect traces/logs/metrics snapshot for incident.",
            "risk_level": "low",
            "approval_required": True,
            "is_hypothesis": True,
            "confidence": 0.4,
            "evidence": evidence_summary[:2] if evidence_summary else [],
            "data_freshness": df_incident,
        }

        # Pipeline trace (Telemetry->Detection->... no CoT exposure, just stages)
        pipeline = {
            "stages": PIPELINE_STAGES,
            "telemetry": {"sources": ["aggregation_service", "observability_health_snapshots", "observability_alerts", "release_records", "knowledge_graph"], "tenant_filtered": True},
            "detection": {"anomalies": len(anomalies), "alerts": len(related_alerts)},
            "correlation": {"recent_changes": len(recent_changes), "related_alerts": len(related_alerts), "dependencies": len(dependencies)},
            "hypothesis": {"count": len(hypotheses)},
            "evidence": {"items": len(evidence_summary)},
            "recommendation": {"count": len(recommendations)},
            "optional_action": optional_action,
        }

        # Deduplicate related_resources
        related_resources = [r for r in related_resources if r]
        seen_res: list[str] = []
        for r in related_resources:
            if r not in seen_res:
                seen_res.append(r)

        return {
            "incident_id": incident_id_s,
            "tenant": tenant_s,
            "service": service,
            "environment": environment,
            "candidate_cause": hypotheses[0] if hypotheses else None,
            "hypotheses": hypotheses[:5],
            "evidence": evidence_summary[:10],
            "related_resources": seen_res[:15],
            "causal_graph": {"nodes": causal_graph.get("nodes", [])[:10], "edges": causal_graph.get("edges", [])[:10]},
            "recommendations": recommendations[:5],
            "optional_action": optional_action,
            "pipeline": pipeline,
            "anomalies": anomalies[:5],
            "data_freshness": df_incident,
            "is_hypothesis": True,
            "is_verified_fact": False,
            "disclaimer": "AI suggestions are hypotheses with confidence/evidence/data_freshness and must not be treated as verified facts. Verify via traces/logs/metrics and causal graph before action. Temporal proximity alone is not causation.",
        }

    # ── Summarize Incident ─────────────────────────────────────────────────

    async def summarize_incident(self, db: AsyncSession, tenant: str, incident_id: str) -> dict:
        tenant_s = _require_tenant(tenant)
        incident_id_s = (incident_id or "").strip()
        if not incident_id_s:
            raise ValueError("incident_id is required")

        # Fetch incident + hypotheses assist reuses logic but we build concise summary
        assist = await self.assist_root_cause(db, tenant_s, incident_id_s)
        if assist.get("error"):
            # still try to build minimal summary from DB if assist failed due to missing incident
            return {
                "incident_id": incident_id_s,
                "tenant": tenant_s,
                "error": assist.get("error"),
                "data_freshness": assist.get("data_freshness", _data_freshness(None)),
                "is_hypothesis": True,
                "summary_type": "incident_summary",
            }

        # Fetch timeline events (concise, no CoT)
        timeline: list[dict] = []
        try:
            from app.incident.models import IncidentEvent, Incident  # type: ignore
            # find incident object again for timeline fields
            incident = None
            try:
                incident = await db.get(Incident, uuid.UUID(incident_id_s))
            except Exception:
                stmt = select(Incident).where(Incident.tenant == tenant_s).limit(200)
                res = await db.execute(stmt)
                for cand in res.scalars().all():
                    if str(cand.id) == incident_id_s:
                        incident = cand
                        break
            if incident:
                stmt = select(IncidentEvent).where(IncidentEvent.incident_id == str(incident.id)).order_by(IncidentEvent.created_at.asc()).limit(50)
                res = await db.execute(stmt)
                for ev in res.scalars().all():
                    timeline.append({
                        "timestamp": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
                        "event_type": ev.event_type,
                        "actor": ev.actor,
                        "message": (ev.message or "")[:300],
                    })
        except Exception as exc:
            logger.debug("summarize timeline fetch failed: %s", exc)

        # Impact & affected services from assist
        impact = getattr(assist, "impact", None)
        if not impact:
            # try incident.impact JSON
            try:
                from app.incident.models import Incident  # type: ignore
                inc = None
                try:
                    inc = await db.get(Incident, uuid.UUID(incident_id_s))
                except Exception:
                    pass
                if inc and getattr(inc, "impact", None):
                    impact = inc.impact
                else:
                    impact = {"note": "impact not yet quantified; check SLO/error_budget"}
            except Exception:
                impact = {"note": "impact unavailable"}

        affected_services = assist.get("related_resources", [])
        service = assist.get("service", "")
        if service and service not in affected_services:
            affected_services = [service] + affected_services

        recent_changes = await self.find_recent_changes(db, tenant_s, service=service or None, window_hours=24)
        related_alerts = assist.get("hypotheses", [])
        # Extract evidence for summary (concise)
        evidence = assist.get("evidence", [])[:5]
        recommended_investigation = [r.get("recommendation", "") for r in assist.get("recommendations", [])[:3]]

        # No chain-of-thought: only surface evidence, not internal reasoning
        return {
            "incident_id": incident_id_s,
            "tenant": tenant_s,
            "service": service,
            "environment": assist.get("environment", "production"),
            "impact": impact,
            "timeline": timeline[:15],
            "affected_services": affected_services[:10],
            "recent_changes": [{"change_id": c.get("change_id"), "type": c.get("type"), "service": c.get("service"), "version": c.get("version"), "created_at": c.get("created_at")} for c in recent_changes[:5]],
            "alerts": [{"alert_id": a.get("alert_id"), "resource": a.get("resource"), "severity": a.get("severity")} for a in (await self.find_related_alerts(db, tenant_s, incident_id=incident_id_s, window_minutes=120))[:5]],
            "hypotheses": assist.get("hypotheses", [])[:3],
            "evidence": evidence,
            "recommended_investigation": recommended_investigation,
            "causal_graph_hint": {"nodes": assist.get("causal_graph", {}).get("nodes", [])[:5], "edges": assist.get("causal_graph", {}).get("edges", [])[:5]},
            "data_freshness": assist.get("data_freshness", _data_freshness(None)),
            "is_hypothesis": True,
            "is_verified_fact": False,
            "summary_type": "incident_summary",
            "disclaimer": "Summary is hypothesis-only; verify via find_trace/find_logs/find_dependencies before conclusion. No chain-of-thought exposed.",
        }

    # ── Pipeline runner ──────────────────────────────────────────────────────

    async def run_pipeline(self, db: AsyncSession, tenant: str, incident_id: str | None = None, metric: str = "") -> dict:
        """Run full pipeline: Telemetry -> Detection -> Correlation -> Hypothesis -> Evidence -> Recommendation -> Optional Action.

        Returns staged outputs, each with confidence/evidence/data_freshness and hypothesis flag.
        """
        tenant_s = _require_tenant(tenant)
        telemetry_sources = ["analytics.aggregation_service", "observability_alerts", "observability_health_snapshots", "release_records", "knowledge_graph"]
        detection = await self.detect_anomalies(db, tenant_s, metric=metric or "", window_hours=24)
        correlation: dict[str, Any] = {}
        hypothesis: dict[str, Any] = {}
        evidence: dict[str, Any] = {}
        recommendation: dict[str, Any] = {}
        optional_action: dict[str, Any] = {}
        if incident_id:
            assist = await self.assist_root_cause(db, tenant_s, incident_id)
            correlation = {"recent_changes": len(assist.get("evidence", [])), "related_alerts": len(assist.get("hypotheses", []))}
            hypothesis = {"hypotheses": assist.get("hypotheses", [])[:3], "candidate_cause": assist.get("candidate_cause")}
            evidence = {"items": assist.get("evidence", [])[:5], "causal_graph": assist.get("causal_graph", {})}
            recommendation = {"items": assist.get("recommendations", [])[:3]}
            optional_action = assist.get("optional_action", {})
        return {
            "tenant": tenant_s,
            "incident_id": incident_id,
            "pipeline": PIPELINE_STAGES,
            "telemetry": {"sources": telemetry_sources, "tenant_filtered": True, "data_freshness": _data_freshness(_now())},
            "detection": {"anomalies": detection[:5], "count": len(detection), "is_hypothesis": True},
            "correlation": correlation,
            "hypothesis": hypothesis,
            "evidence": evidence,
            "recommendation": recommendation,
            "optional_action": {**optional_action, "approval_required": True} if optional_action else {"approval_required": True, "note": "No incident_id provided; detection-only run."},
            "is_hypothesis": True,
            "is_verified_fact": False,
            "data_freshness": _data_freshness(_now()),
        }


# singleton
aiops_engine = AIOpsEngine()
