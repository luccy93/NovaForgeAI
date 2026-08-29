"""Detection engine — Volume 63.

Evaluate normalized security events against active versioned rules.
Bounded queries and time windows. Supports threshold/sequence/frequency/absence/
correlation/anomaly/policy_violation.
"""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import SecOpsAlert, SecOpsDetectionRule

# Bounded defaults
MAX_EVENTS_PER_EVAL = 1000
MAX_TIME_WINDOW_SECONDS = 3600  # 1h max

def _bounded_window(seconds: int) -> int:
    return min(max(seconds, 1), MAX_TIME_WINDOW_SECONDS)

def _fingerprint(rule_id: str, tenant: str, severity: str, resource: str = "") -> str:
    raw = f"{rule_id}:{tenant}:{severity}:{resource}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _parse_ts(ts: str) -> datetime:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now(timezone.utc)

async def list_active_rules(db: AsyncSession, tenant: str) -> list[SecOpsDetectionRule]:
    res = await db.execute(select(SecOpsDetectionRule).where(SecOpsDetectionRule.tenant == tenant, SecOpsDetectionRule.enabled == True).order_by(SecOpsDetectionRule.version.desc()))  # noqa: E712
    return list(res.scalars().all())

async def create_rule(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> SecOpsDetectionRule:
    # Validate
    rule_type = payload.get("rule_type") or payload.get("type")
    if rule_type not in {"threshold", "sequence", "frequency", "absence", "correlation", "anomaly", "policy_violation"}:
        raise ValueError(f"invalid rule_type {rule_type}")
    category = (payload.get("category") or "APPLICATION").upper()
    severity = (payload.get("severity") or "MEDIUM").upper()
    # version bump per name
    existing = await db.execute(select(SecOpsDetectionRule).where(SecOpsDetectionRule.tenant == tenant, SecOpsDetectionRule.name == payload["name"]).order_by(SecOpsDetectionRule.version.desc()))
    prev = existing.scalars().first()
    next_ver = (prev.version + 1) if prev else 1
    rule = SecOpsDetectionRule(
        tenant=tenant,
        name=payload["name"],
        description=payload.get("description", ""),
        category=category,
        severity=severity,
        rule_type=rule_type,
        enabled=payload.get("enabled", True),
        version=next_ver,
        conditions=payload.get("conditions", {}),
        threshold=payload.get("threshold", {}),
        time_window_seconds=_bounded_window(int(payload.get("time_window_seconds", 300))),
        confidence=float(payload.get("confidence", 0.7)),
        owner=payload.get("owner", ""),
        created_by=created_by,
        baseline_config=payload.get("baseline_config", {}),
        change_reason=payload.get("change_reason", ""),
    )
    db.add(rule)
    await db.flush()
    return rule

def _evaluate_threshold(events: list[dict], rule: SecOpsDetectionRule) -> bool:
    thresh = int(rule.threshold.get("count", rule.threshold.get("threshold", 5)))
    window = _bounded_window(rule.time_window_seconds)
    # count events matching conditions
    matched = _filter_by_conditions(events, rule.conditions)
    if len(matched) >= thresh:
        # check within window
        if len(matched) == 0:
            return False
        sorted_m = sorted(matched, key=lambda e: _parse_ts(e.get("timestamp", "")))
        # sliding window count
        for i in range(len(sorted_m)):
            start = _parse_ts(sorted_m[i].get("timestamp", ""))
            cnt = 1
            for j in range(i+1, len(sorted_m)):
                if (_parse_ts(sorted_m[j].get("timestamp", "")) - start).total_seconds() <= window:
                    cnt += 1
                    if cnt >= thresh:
                        return True
                else:
                    break
        return cnt >= thresh # fallback
    return False

def _evaluate_sequence(events: list[dict], rule: SecOpsDetectionRule) -> bool:
    # conditions as {sequence: [{actor, action}, ...]}
    seq = rule.conditions.get("sequence") or rule.threshold.get("sequence")
    if not seq or not isinstance(seq, list):
        return False
    window = _bounded_window(rule.time_window_seconds)
    sorted_e = sorted(events, key=lambda e: _parse_ts(e.get("timestamp", "")))
    # check ordered occurrence
    idx = 0
    start_ts = None
    for ev in sorted_e:
        cond = seq[idx]
        if _event_matches(ev, cond):
            if idx == 0:
                start_ts = _parse_ts(ev.get("timestamp", ""))
            idx += 1
            if idx == len(seq):
                # check window from start to current
                cur_ts = _parse_ts(ev.get("timestamp", ""))
                if start_ts and (cur_ts - start_ts).total_seconds() <= window:
                    return True
                # reset
                idx = 0
                start_ts = None
        # optional: reset if out of window
        if start_ts and (_parse_ts(ev.get("timestamp", "")) - start_ts).total_seconds() > window:
            idx = 0
            start_ts = None
    return False

def _evaluate_frequency(events: list[dict], rule: SecOpsDetectionRule) -> bool:
    # frequency: events per window > rate
    rate = float(rule.threshold.get("rate", rule.threshold.get("events_per_minute", 10)))
    window = _bounded_window(rule.time_window_seconds)
    matched = _filter_by_conditions(events, rule.conditions)
    per_min = len(matched) / max(window / 60.0, 1)
    return per_min >= rate

def _evaluate_absence(events: list[dict], rule: SecOpsDetectionRule) -> bool:
    # absence: expected heartbeat missing
    expected_source = rule.conditions.get("source") or rule.conditions.get("expected_source")
    window = _bounded_window(rule.time_window_seconds)
    if not expected_source:
        return False
    # if no event from source in window -> true
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
    for ev in events:
        if ev.get("source") == expected_source and _parse_ts(ev.get("timestamp", "")) >= cutoff:
            return False
    return True

def _evaluate_correlation(events: list[dict], rule: SecOpsDetectionRule) -> bool:
    keys = rule.conditions.get("correlation_keys") or ["actor", "resource"]
    min_count = int(rule.threshold.get("count", 2))
    from app.secops.correlation import correlate_events
    groups = correlate_events(events, time_window_seconds=_bounded_window(rule.time_window_seconds))
    for g in groups:
        if g["key_type"] in keys and g["count"] >= min_count:
            return True
    return False

def _evaluate_policy_violation(events: list[dict], rule: SecOpsDetectionRule) -> bool:
    # policy violation if any event has policy_violation flag or matches policy condition
    policy_id = rule.conditions.get("policy_id")
    for ev in events:
        meta = ev.get("source_metadata", {})
        if meta.get("policy_violation") or ev.get("policy_violation"):
            if policy_id:
                if meta.get("policy_id") == policy_id or ev.get("policy") == policy_id:
                    return True
            else:
                return True
        # also check action == policy violation
        if ev.get("category") == "CONFIGURATION" and "violation" in ev.get("action", "").lower():
            return True
    return False

def _filter_by_conditions(events: list[dict], conditions: dict) -> list[dict]:
    if not conditions:
        return events
    out = []
    for ev in events:
        if _event_matches(ev, conditions):
            out.append(ev)
    return out

def _event_matches(event: dict, cond: dict) -> bool:
    for k, v in cond.items():
        if k in {"sequence", "correlation_keys", "expected_source", "policy_id"}:
            continue
        ev_val = event.get(k) or event.get("source_metadata", {}).get(k)
        if isinstance(v, list):
            if ev_val not in v:
                return False
        elif isinstance(v, dict) and "$in" in v:
            if ev_val not in v["$in"]:
                return False
        else:
            if str(ev_val) != str(v):
                return False
    return True

async def evaluate_rules(db: AsyncSession, tenant: str, events: list[dict]) -> list[SecOpsAlert]:
    """Evaluate events against active rules, create alerts (bounded)."""
    if len(events) > MAX_EVENTS_PER_EVAL:
        events = events[-MAX_EVENTS_PER_EVAL:]
    # tenant isolation: filter events
    tenant_events = [e for e in events if e.get("tenant") == tenant]
    rules = await list_active_rules(db, tenant)
    alerts: list[SecOpsAlert] = []
    for rule in rules:
        triggered = False
        if rule.rule_type == "threshold":
            triggered = _evaluate_threshold(tenant_events, rule)
        elif rule.rule_type == "sequence":
            triggered = _evaluate_sequence(tenant_events, rule)
        elif rule.rule_type == "frequency":
            triggered = _evaluate_frequency(tenant_events, rule)
        elif rule.rule_type == "absence":
            triggered = _evaluate_absence(tenant_events, rule)
        elif rule.rule_type == "correlation":
            triggered = _evaluate_correlation(tenant_events, rule)
        elif rule.rule_type == "anomaly":
            # delegate to anomaly detector advisory — only trigger if confidence high and explicitly configured
            # For now, skip auto-trigger; anomaly worker will create alerts separately
            triggered = False
        elif rule.rule_type == "policy_violation":
            triggered = _evaluate_policy_violation(tenant_events, rule)
        if triggered:
            # deduplication: fingerprint per rule+tenant+severity
            fp = _fingerprint(str(rule.id), tenant, rule.severity, rule.name)
            # check existing open alert with same fingerprint not suppressed
            existing = await db.execute(select(SecOpsAlert).where(SecOpsAlert.tenant == tenant, SecOpsAlert.fingerprint == fp, SecOpsAlert.status.in_(["OPEN", "ACKNOWLEDGED", "INVESTIGATING"])))  # noqa: E712
            if existing.scalars().first():
                continue  # dedup - do not duplicate
            # suppression check
            # (suppression handled via query of rules? simplified: if rule has suppression window, skip)
            alert = SecOpsAlert(
                tenant=tenant,
                rule_id=rule.id,
                rule_version=rule.version,
                rule_name=rule.name,
                events=tenant_events[:10],  # bounded store
                severity=rule.severity,
                status="OPEN",
                confidence=rule.confidence,
                fingerprint=fp,
                deduplication_key=fp,
            )
            db.add(alert)
            await db.flush()
            alerts.append(alert)
    return alerts
