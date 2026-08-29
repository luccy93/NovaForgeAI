"""Posture, coverage, SLO, analytics — Volume 63 Commit 2.

Do not present posture as certification. Track SLOs.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import SecOpsAlert, SecOpsDetectionRule, SecOpsFinding, SecOpsCase


async def get_posture(db: AsyncSession, tenant: str) -> dict:
    rules = (await db.execute(select(SecOpsDetectionRule).where(SecOpsDetectionRule.tenant == tenant))).scalars().all()
    alerts = (await db.execute(select(SecOpsAlert).where(SecOpsAlert.tenant == tenant))).scalars().all()
    findings = (await db.execute(select(SecOpsFinding).where(SecOpsFinding.tenant == tenant))).scalars().all()
    cases = (await db.execute(select(SecOpsCase).where(SecOpsCase.tenant == tenant))).scalars().all()
    # posture indicators configurable, not certification
    indicators = {
        "rules_enabled": len([r for r in rules if r.enabled]),
        "rules_total": len(rules),
        "alerts_open": len([a for a in alerts if a.status == "OPEN"]),
        "findings_open": len([f for f in findings if f.status == "OPEN"]),
        "cases_open": len([c for c in cases if c.status in {"OPEN","INVESTIGATING"}]),
        "has_mfa": False,  # would check iam
        "has_logging": True,
    }
    return {
        "tenant": tenant,
        "indicators": indicators,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Posture indicators — not certification",
    }


async def get_coverage(db: AsyncSession, tenant: str) -> dict:
    rules = (await db.execute(select(SecOpsDetectionRule).where(SecOpsDetectionRule.tenant == tenant))).scalars().all()
    # asset coverage: count distinct resources vs rules coverage
    categories_covered = {r.category for r in rules if r.enabled}
    all_categories = {"AUTHENTICATION","AUTHORIZATION","NETWORK","APPLICATION","DATA","AI","AGENT","CLOUD","ENDPOINT","SUPPLY_CHAIN","CONFIGURATION","IDENTITY"}
    uncovered = all_categories - categories_covered
    gaps = []
    if uncovered:
        gaps.append({"type": "rule_coverage", "uncovered_categories": list(uncovered)})
    # event coverage: check recent events categories vs rules
    from app.secops.normalization import get_recent_events
    events = get_recent_events(tenant=tenant, limit=100)
    event_cats = {e.get("category") for e in events}
    if not events:
        gaps.append({"type": "logging", "detail": "no events ingested — no logging"})
    return {
        "tenant": tenant,
        "asset_coverage": {"categories_covered": len(categories_covered), "total": len(all_categories)},
        "event_coverage": len(event_cats),
        "rule_coverage": len([r for r in rules if r.enabled]),
        "response_coverage": len(rules),  # proxy
        "gaps": gaps,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_slo(db: AsyncSession, tenant: str) -> dict:
    # SLO targets configurable: alert_processing, detection_latency, response_latency
    alerts = (await db.execute(select(SecOpsAlert).where(SecOpsAlert.tenant == tenant))).scalars().all()
    # detection latency: event timestamp -> alert created_at
    latencies = []
    for a in alerts[:20]:
        if a.events and a.created_at:
            try:
                ev_ts = a.events[0].get("timestamp") if isinstance(a.events[0], dict) else None
                if ev_ts:
                    ev_dt = datetime.fromisoformat(ev_ts.replace("Z","+00:00"))
                    lat = (a.created_at - ev_dt).total_seconds()
                    latencies.append(lat)
            except Exception:
                pass
    avg_lat = sum(latencies)/len(latencies) if latencies else 0
    return {
        "tenant": tenant,
        "slo_targets": {"alert_processing_seconds": 60, "detection_latency_seconds": 30, "response_latency_seconds": 300},
        "observed": {"detection_latency_avg_seconds": round(avg_lat,2), "alerts_measured": len(latencies)},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
