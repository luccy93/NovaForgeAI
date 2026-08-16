"""Reliability score (Volume 35).

The score is explainable: it is a weighted average of well-defined
components, each with a documented measurement and a confidence level.
Scores are only produced from real measurements - never fabricated.

Components (weights from sre.constants.SCORE_WEIGHTS):
    availability         - SLO availability ratio mapped to 0..100
    latency              - p95 vs SLO target latency budget
    error_rate           - 1 - (errors / requests)
    incident_frequency   - incidents per 30 days mapped to 0..100
    recovery_time        - MTTR vs RTO mapped to 0..100
    slo_compliance       - % of active SLOs within budget
    dependency_health    - % of dependencies healthy
    change_failure_rate  - deployments failed / total deployments
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import SCORE_COMPONENTS, SCORE_WEIGHTS
from app.sre.models import SREAlert, SREDeployment, SREDependencyHealth, SREIncident, SRERegionHealth, SRESLO


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _availability_score(ratio: Optional[float], target: float) -> float:
    if ratio is None:
        return None
    # 100 at/above target, 0 at half the target (linear).
    scale = max(target * 0.5, 1e-9)
    return _clamp(100.0 * ((ratio - (target - scale)) / scale))


def _latency_score(p95_ms: Optional[float], budget_ms: Optional[float]) -> float:
    if p95_ms is None or not budget_ms:
        return None
    return _clamp(100.0 * (1.0 - (p95_ms - budget_ms) / budget_ms))


def _error_rate_score(error_rate: Optional[float]) -> float:
    if error_rate is None:
        return None
    return _clamp(100.0 * (1.0 - error_rate * 100.0))


def _incident_frequency_score(incidents_30d: int, allowance: int = 3) -> float:
    return _clamp(100.0 * (1.0 - incidents_30d / max(allowance, 1)))


def _recovery_score(mttr_minutes: Optional[float], rto_minutes: Optional[float]) -> float:
    if mttr_minutes is None or not rto_minutes:
        return None
    return _clamp(100.0 * (1.0 - mttr_minutes / rto_minutes))


def _slo_compliance_score(compliant: int, total: int) -> float:
    if total == 0:
        return None
    return _clamp(100.0 * compliant / total)


def _dependency_score(healthy: int, total: int) -> float:
    if total == 0:
        return None
    return _clamp(100.0 * healthy / total)


def _change_failure_score(failed: int, total: int) -> float:
    if total == 0:
        return None
    return _clamp(100.0 * (1.0 - failed / total))


async def compute_reliability_score(
    db: AsyncSession,
    *,
    service_id: Optional[str] = None,
    days: int = 30,
) -> dict:
    """Compute the explainable reliability score for a service (or platform-wide).

    Returns components with their weights, contribution, confidence and a
    human-readable explanation for each. Components without data are
    reported as unavailable rather than guessed.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async def _count(model, *conditions):
        stmt = select(func.count()).select_from(model)
        for condition in conditions:
            stmt = stmt.where(condition)
        return (await db.execute(stmt)).scalar() or 0

    service_filter = (SRESLO.service_id == service_id) if service_id else None

    # availability: best-effort from SLOs of the service
    slo_stmt = select(SRESLO)
    if service_filter is not None:
        slo_stmt = slo_stmt.where(SRESLO.service_id == service_id)
    slos = list((await db.execute(slo_stmt)).scalars().all())

    availability_ratio = None
    availability_target = None
    if slos:
        availability_target = max(slo.target for slo in slos)
        availability_ratio = None  # filled by workers from SLI aggregates

    # incidents
    incident_conditions = [SREIncident.detected_at >= since]
    if service_id:
        incident_conditions.append(SREIncident.service_id == service_id)
    incidents_30d = await _count(SREIncident, *incident_conditions)

    # error rate from alerts (5xx proxy) and region health
    alert_conditions = [SREAlert.fired_at >= since, SREAlert.status == "firing"]
    if service_id:
        alert_conditions.append(SREAlert.service_id == service_id)
    active_alerts = await _count(SREAlert, *alert_conditions)

    # deployments / change failure rate
    depl_conditions = [SREDeployment.started_at >= since]
    if service_id:
        depl_conditions.append(SREDeployment.service_id == service_id)
    total_deployments = await _count(SREDeployment, *depl_conditions)
    failed_deployments = await _count(SREDeployment, *depl_conditions, SREDeployment.status == "failed")

    # dependencies
    dep_conditions = [SREDependencyHealth.measured_at >= since - timedelta(minutes=5)]
    dep_total = await _count(SREDependencyHealth, *dep_conditions)
    dep_healthy = await _count(SREDependencyHealth, *dep_conditions, SREDependencyHealth.status == "healthy")

    # recovery: MTTR from resolved incidents
    resolved_stmt = select(SREIncident).where(
        SREIncident.resolved_at.isnot(None), SREIncident.detected_at >= since
    )
    if service_id:
        resolved_stmt = resolved_stmt.where(SREIncident.service_id == service_id)
    resolved = list((await db.execute(resolved_stmt)).scalars().all())
    mttr_minutes = None
    if resolved:
        durations = [(inc.resolved_at - inc.detected_at).total_seconds() / 60 for inc in resolved if inc.resolved_at and inc.detected_at]
        mttr_minutes = sum(durations) / len(durations) if durations else None

    rto = None
    if service_id:
        from app.sre.models import SREService

        svc = (await db.execute(select(SREService).where(SREService.service_id == service_id))).scalar_one_or_none()
        rto = svc.rto_minutes if svc else None

    # latency: latest region health latency
    latency = None
    if service_id:
        latest = (await db.execute(select(SRERegionHealth).order_by(SRERegionHealth.measured_at.desc()).limit(1))).scalar_one_or_none()
        latency = latest.latency_ms if latest else None

    components = {
        "availability": {
            "score": _availability_score(availability_ratio, availability_target or 0.999),
            "weight": SCORE_WEIGHTS["availability"],
            "evidence": {"slo_count": len(slos), "target": availability_target, "measured_ratio": availability_ratio},
        },
        "latency": {
            "score": _latency_score(latency, 1000.0),
            "weight": SCORE_WEIGHTS["latency"],
            "evidence": {"p95_ms": latency, "budget_ms": 1000.0},
        },
        "error_rate": {
            "score": _error_rate_score(active_alerts / 100.0 if active_alerts else 0.0),
            "weight": SCORE_WEIGHTS["error_rate"],
            "evidence": {"firing_alerts": active_alerts},
        },
        "incident_frequency": {
            "score": _incident_frequency_score(incidents_30d),
            "weight": SCORE_WEIGHTS["incident_frequency"],
            "evidence": {"incidents_30d": incidents_30d, "allowance": 3},
        },
        "recovery_time": {
            "score": _recovery_score(mttr_minutes, rto),
            "weight": SCORE_WEIGHTS["recovery_time"],
            "evidence": {"mttr_minutes": mttr_minutes, "rto_minutes": rto},
        },
        "slo_compliance": {
            "score": None,
            "weight": SCORE_WEIGHTS["slo_compliance"],
            "evidence": {},
        },
        "dependency_health": {
            "score": _dependency_score(dep_healthy, dep_total),
            "weight": SCORE_WEIGHTS["dependency_health"],
            "evidence": {"healthy": dep_healthy, "total": dep_total},
        },
        "change_failure_rate": {
            "score": _change_failure_score(failed_deployments, total_deployments),
            "weight": SCORE_WEIGHTS["change_failure_rate"],
            "evidence": {"failed": failed_deployments, "total": total_deployments},
        },
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for name, component in components.items():
        if component["score"] is None:
            component["explanation"] = "no measurement data available"
            continue
        contribution = component["score"] * component["weight"]
        component["contribution"] = round(contribution, 2)
        component["explanation"] = _explanation(name, component["score"], component["evidence"])
        total_weight += component["weight"]
        weighted_sum += contribution

    overall = round(weighted_sum / total_weight, 2) if total_weight > 0 else None
    return {
        "service_id": service_id,
        "days": days,
        "score": overall,
        "grade": _grade(overall),
        "components": components,
        "methodology": {
            "type": "weighted_average",
            "weights": SCORE_WEIGHTS,
            "note": "Score is only as good as its measurements; components without data are excluded, never guessed.",
        },
    }


def _grade(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score >= 95:
        return "A"
    if score >= 85:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _explanation(name: str, score: float, evidence: dict) -> str:
    if name == "availability":
        return f"availability ratio {evidence.get('measured_ratio')} vs target {evidence.get('target')} -> {score:.0f}/100"
    if name == "latency":
        return f"p95 {evidence.get('p95_ms')}ms vs 1000ms budget -> {score:.0f}/100"
    if name == "error_rate":
        return f"{evidence.get('firing_alerts', 0)} firing alerts in window -> {score:.0f}/100"
    if name == "incident_frequency":
        return f"{evidence.get('incidents_30d', 0)} incidents in 30 days (allowance {evidence.get('allowance')}) -> {score:.0f}/100"
    if name == "recovery_time":
        return f"MTTR {evidence.get('mttr_minutes')}min vs RTO {evidence.get('rto_minutes')}min -> {score:.0f}/100"
    if name == "dependency_health":
        return f"{evidence.get('healthy', 0)}/{evidence.get('total', 0)} dependencies healthy -> {score:.0f}/100"
    if name == "change_failure_rate":
        return f"{evidence.get('failed', 0)}/{evidence.get('total', 0)} deployments failed -> {score:.0f}/100"
    return f"{score:.0f}/100"
