"""Investigation service — Volume 63.

Provide timeline ordered by timestamp/source, never fabricate missing events.
Evidence each item includes source/timestamp/resource/event/confidence, integrity via audit.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import SecOpsAlert, SecOpsCase, SecOpsCaseEvidence

def _to_uuid(v):
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


def _parse_ts(ts: str) -> datetime:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now(timezone.utc)

async def build_investigation(db: AsyncSession, tenant: str, case_or_alert_id: str) -> dict:
    # try case first
    case = None
    alert = None
    # case lookup
    try:
        from uuid import UUID
        UUID(case_or_alert_id)
    except Exception:
        pass
    # attempt case
    res_case = await db.execute(select(SecOpsCase).where(SecOpsCase.id == _to_uuid(case_or_alert_id), SecOpsCase.tenant == tenant))
    case = res_case.scalar_one_or_none()
    if case:
        # evidence timeline
        res_ev = await db.execute(select(SecOpsCaseEvidence).where(SecOpsCaseEvidence.tenant == tenant, SecOpsCaseEvidence.case_id == case.id).order_by(SecOpsCaseEvidence.timestamp.asc()))
        evidences = list(res_ev.scalars().all())
        timeline=[]
        for ev in evidences:
            timeline.append({"timestamp": ev.timestamp.isoformat() if ev.timestamp else "", "source": ev.source, "resource": ev.resource, "event": ev.event, "confidence": ev.confidence, "integrity_hash": ev.integrity_hash})
        # alerts linked
        alert_ids = case.alerts or []
        alerts=[]
        for aid in alert_ids:
            try:
                r = await db.execute(select(SecOpsAlert).where(SecOpsAlert.id == _to_uuid(aid), SecOpsAlert.tenant == tenant))
                a = r.scalar_one_or_none()
                if a:
                    alerts.append({"id": str(a.id), "severity": a.severity, "status": a.status, "rule_name": a.rule_name, "fingerprint": a.fingerprint})
            except Exception:
                continue
        timeline_sorted = sorted(timeline, key=lambda x: _parse_ts(x.get("timestamp","")))
        return {
            "case_id": str(case.id),
            "tenant": tenant,
            "status": case.status,
            "severity": case.severity,
            "owner": case.owner,
            "alerts": alerts,
            "findings": case.findings,
            "timeline": timeline_sorted,
            "evidence_count": len(timeline_sorted),
            "incident_id": case.incident_id,
        }
    # try alert
    res_alert = await db.execute(select(SecOpsAlert).where(SecOpsAlert.id == _to_uuid(case_or_alert_id), SecOpsAlert.tenant == tenant))
    alert = res_alert.scalar_one_or_none()
    if alert:
        events = alert.events or []
        timeline=[]
        for ev in events:
            if isinstance(ev, dict):
                timeline.append({"timestamp": ev.get("timestamp",""), "source": ev.get("source",""), "resource": ev.get("resource",""), "event": ev, "confidence": alert.confidence})
        timeline_sorted = sorted(timeline, key=lambda x: _parse_ts(x.get("timestamp","")))
        return {
            "alert_id": str(alert.id),
            "tenant": tenant,
            "status": alert.status,
            "severity": alert.severity,
            "rule_name": alert.rule_name,
            "timeline": timeline_sorted,
            "evidence_count": len(timeline_sorted),
        }
    raise ValueError("case or alert not found")
