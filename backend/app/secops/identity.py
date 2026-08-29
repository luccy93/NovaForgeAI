"""Identity threat detection — Volume 63.

Detect repeated failed auth, privilege escalation, unexpected admin actions, credential misuse.
Do not make unsupported identity claims — require strong evidence.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

def _parse_ts(ts: str) -> datetime:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now(timezone.utc)

def detect_repeated_failed_auth(events: list[dict], tenant: str, threshold: int = 5, window_seconds: int = 300) -> list[dict]:
    """Repeated failed authentication per actor within window."""
    findings=[]
    by_actor: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e.get("tenant")!=tenant: continue
        if e.get("category")!="AUTHENTICATION": continue
        if "failed" not in e.get("action","").lower(): continue
        by_actor[e.get("actor","")].append(e)
    for actor, evs in by_actor.items():
        if not actor: continue
        sorted_evs = sorted(evs, key=lambda x: _parse_ts(x.get("timestamp","")))
        # sliding window
        for i in range(len(sorted_evs)):
            cnt=1
            start=_parse_ts(sorted_evs[i].get("timestamp",""))
            for j in range(i+1, len(sorted_evs)):
                if (_parse_ts(sorted_evs[j].get("timestamp",""))-start).total_seconds() <= window_seconds:
                    cnt+=1
                    if cnt>=threshold:
                        findings.append({"actor": actor, "type": "repeated_failed_auth", "count": cnt, "window_seconds": window_seconds, "evidence": sorted_evs[i:j+1], "confidence": 0.85})
                        break
                else:
                    break
    return findings

def detect_privilege_escalation(events: list[dict], tenant: str) -> list[dict]:
    findings=[]
    for e in events:
        if e.get("tenant")!=tenant: continue
        action = e.get("action","").lower()
        if any(k in action for k in ["role_change", "permission_change", "privilege_escalation", "grant_admin", "elevate"]):
            # require evidence: actor != target or role escalation
            meta = e.get("source_metadata",{})
            old_role = meta.get("old_role") or meta.get("previous_role")
            new_role = meta.get("new_role") or meta.get("role")
            if old_role and new_role and old_role != new_role:
                findings.append({"actor": e.get("actor"), "type": "privilege_escalation", "from": old_role, "to": new_role, "event": e, "confidence": 0.9})
            elif "escalation" in action:
                findings.append({"actor": e.get("actor"), "type": "privilege_escalation", "event": e, "confidence": 0.7})
    return findings

def detect_unexpected_admin(events: list[dict], tenant: str) -> list[dict]:
    findings=[]
    for e in events:
        if e.get("tenant")!=tenant: continue
        if e.get("category") not in {"AUTHORIZATION","IDENTITY","CONFIGURATION"}: continue
        if "admin" in e.get("action","").lower() or "break_glass" in e.get("action","").lower():
            # unexpected if actor not in known admin list (simplified: treat all admin actions as needing review)
            findings.append({"actor": e.get("actor"), "type": "unexpected_admin_action", "action": e.get("action"), "event": e, "confidence": 0.6})
    return findings

def detect_credential_misuse(events: list[dict], tenant: str) -> list[dict]:
    findings=[]
    # API abuse with credential misuse: same credential from multiple IPs
    by_actor_ip: dict[str, set] = defaultdict(set)
    for e in events:
        if e.get("tenant")!=tenant: continue
        if e.get("ip") and e.get("actor"):
            by_actor_ip[e.get("actor")].add(e.get("ip"))
    for actor, ips in by_actor_ip.items():
        if len(ips) >= 3:
            findings.append({"actor": actor, "type": "credential_misuse", "ips": list(ips), "confidence": 0.75})
    return findings

def detect_all_identity(events: list[dict], tenant: str) -> list[dict]:
    out=[]
    out.extend(detect_repeated_failed_auth(events, tenant))
    out.extend(detect_privilege_escalation(events, tenant))
    out.extend(detect_unexpected_admin(events, tenant))
    out.extend(detect_credential_misuse(events, tenant))
    return out
