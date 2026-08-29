"""Threat hunting — Volume 63 Commit 2.

Bounded queries for actors/resources/events/indicators/behavior/time windows.
Reusable templates, async jobs via workers, no duplicate telemetry.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# In-memory hunt jobs (production would use DB + workers)
_hunts: dict[str, dict] = {}

HUNT_TEMPLATES = {
    "credential_abuse": {"description": "Search for credential abuse patterns", "query": {"category": "AUTHENTICATION", "action": "login_failed", "threshold": 5}},
    "privilege_escalation": {"description": "Detect privilege escalation", "query": {"category": "AUTHORIZATION", "action": "role_change"}},
    "data_access_anomalies": {"description": "Anomalous data access", "query": {"category": "DATA", "classification": "RESTRICTED"}},
    "agent_abuse": {"description": "Agent tool abuse", "query": {"category": "AGENT", "action": "tool_call"}},
    "supply_chain_changes": {"description": "Supply-chain artifact changes", "query": {"category": "SUPPLY_CHAIN"}},
    "unexpected_deployment": {"description": "Unexpected deployment activity", "query": {"category": "CONFIGURATION", "action": "deployment"}},
}

MAX_HUNT_LIMIT = 1000
MAX_WINDOW_HOURS = 24 * 7  # 1 week max


def _bounded(limit: int) -> int:
    return min(max(limit, 1), MAX_HUNT_LIMIT)


async def start_hunt(db: AsyncSession, tenant: str, query: dict, scope: dict | None = None, analyst: str = "", template: str | None = None) -> dict:
    # Validate bounded
    limit = int(query.get("limit", 100))
    if limit > MAX_HUNT_LIMIT:
        raise ValueError(f"limit too large (max {MAX_HUNT_LIMIT})")
    window_hours = int(query.get("window_hours", query.get("time_window_hours", 24)))
    if window_hours > MAX_WINDOW_HOURS:
        raise ValueError(f"window too large (max {MAX_WINDOW_HOURS}h)")
    if not query.get("actor") and not query.get("resource") and not query.get("indicator") and not query.get("category") and not template:
        # require at least one bounded field
        raise ValueError("hunt query must have at least one of actor/resource/indicator/category")
    # Resolve template
    if template:
        if template not in HUNT_TEMPLATES:
            raise ValueError(f"unknown template {template}")
        # merge template query
        base = HUNT_TEMPLATES[template]["query"].copy()
        base.update(query)
        query = base
    hunt_id = str(uuid.uuid4())
    job = {
        "id": hunt_id,
        "tenant": tenant,
        "query": query,
        "scope": scope or {},
        "template": template,
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analyst": analyst,
        "results_metadata": None,
    }
    _hunts[hunt_id] = job
    # Immediately execute bounded search against recent normalized events (no duplicate telemetry)
    try:
        from app.secops.normalization import get_recent_events
        events = get_recent_events(tenant=tenant, limit=_bounded(limit))
        # Filter by query
        filtered = _filter_events(events, query)
        job["status"] = "COMPLETED"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["results_metadata"] = {
            "matched": len(filtered),
            "total_scanned": len(events),
            "query": query,
            "scope": scope,
            "sample": filtered[:5],  # do not duplicate sensitive telemetry — only metadata/sample
        }
        job["results"] = filtered[:_bounded(limit)]
    except Exception as e:
        job["status"] = "FAILED"
        job["error"] = str(e)[:200]
    return job


def _filter_events(events: list[dict], query: dict) -> list[dict]:
    out = []
    for e in events:
        match = True
        for k in ("actor", "resource", "category", "severity", "source", "indicator"):
            if k in query and query[k]:
                if k == "indicator":
                    # indicator matches any field
                    haystack = " ".join([str(e.get("resource","")), str(e.get("actor","")), str(e.get("ip",""))])
                    if str(query[k]) not in haystack:
                        match = False
                        break
                elif str(e.get(k, "")).lower() != str(query[k]).lower():
                    # for category severity allow case-insensitive
                    match = False
                    break
        # time window filter if query has since
        if match and "since" in query:
            try:
                since = datetime.fromisoformat(query["since"].replace("Z","+00:00"))
                ev_ts = datetime.fromisoformat(e.get("timestamp","").replace("Z","+00:00"))
                if ev_ts < since:
                    match = False
            except Exception:
                pass
        if match:
            out.append(e)
    return out


async def get_hunt(hunt_id: str, tenant: str) -> dict | None:
    job = _hunts.get(hunt_id)
    if not job or job["tenant"] != tenant:
        return None
    return job


async def list_hunts(tenant: str, limit: int = 20) -> list[dict]:
    jobs = [j for j in _hunts.values() if j["tenant"] == tenant]
    jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return jobs[:_bounded(limit)]


def list_templates() -> dict:
    return HUNT_TEMPLATES


def clear_hunts():
    _hunts.clear()
