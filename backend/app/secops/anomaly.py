"""Anomaly detection — Volume 63.

Detect unusual authentication/API usage/data access/agent activity/deployment/network.
Maintain configurable baselines, never treat limited data as reliable.
AI-assisted advisory unless explicitly configured.
"""

import math
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Any

MIN_SAMPLES_FOR_BASELINE = 100
ANOMALY_THRESHOLD_STD = 2.5


class BaselineStore:
    """In-memory baseline store (real impl would persist to analytics_aggregates)."""

    def __init__(self):
        # key -> {count, mean, std, samples}
        self._baselines: dict[str, dict] = {}
        self._samples: dict[str, list[float]] = defaultdict(list)

    def _key(self, tenant: str, category: str, actor: str, action: str) -> str:
        return f"{tenant}:{category}:{actor}:{action}"

    def record(self, tenant: str, category: str, actor: str, action: str, value: float = 1.0) -> None:
        k = self._key(tenant, category, actor, action)
        self._samples[k].append(value)
        # keep bounded 1000
        if len(self._samples[k]) > 1000:
            self._samples[k] = self._samples[k][-1000:]
        samples = self._samples[k]
        if len(samples) >= 10:
            mean = sum(samples) / len(samples)
            var = sum((x - mean) ** 2 for x in samples) / len(samples)
            std = math.sqrt(var) if var > 0 else 1.0
            self._baselines[k] = {"count": len(samples), "mean": mean, "std": std, "reliable": len(samples) >= MIN_SAMPLES_FOR_BASELINE}

    def is_anomalous(self, tenant: str, category: str, actor: str, action: str, value: float = 1.0) -> tuple[bool, dict]:
        k = self._key(tenant, category, actor, action)
        baseline = self._baselines.get(k)
        if not baseline:
            return False, {"reason": "no baseline", "reliable": False}
        if not baseline.get("reliable"):
            return False, {"reason": "insufficient data", "count": baseline["count"], "reliable": False}
        mean, std = baseline["mean"], baseline["std"]
        if std == 0:
            std = 1.0
        z = abs(value - mean) / std
        is_anom = z >= ANOMALY_THRESHOLD_STD
        return is_anom, {"z_score": z, "mean": mean, "std": std, "value": value, "reliable": True}

    def get_baseline(self, tenant: str, category: str, actor: str, action: str) -> dict | None:
        return self._baselines.get(self._key(tenant, category, actor, action))

    def clear(self) -> None:
        self._baselines.clear()
        self._samples.clear()


baseline_store = BaselineStore()


def detect_unusual_auth(events: list[dict], tenant: str) -> list[dict]:
    out = []
    for e in events:
        if e.get("tenant") != tenant:
            continue
        if e.get("category") != "AUTHENTICATION":
            continue
        actor = e.get("actor", "")
        # track failed auth count per actor
        baseline_store.record(tenant, "AUTHENTICATION", actor, e.get("action", ""), 1.0)
        # simplistic: if action is failed login and count anomalous
        if "failed" in e.get("action", "").lower():
            is_anom, meta = baseline_store.is_anomalous(tenant, "AUTHENTICATION", actor, e.get("action", ""), 1.0)
            # for testing with limited data, use frequency heuristic fallback
            # count failed in recent events for actor
            recent_failed = [x for x in events if x.get("actor") == actor and "failed" in x.get("action","").lower()]
            if len(recent_failed) >= 5 and not is_anom:
                out.append({"event": e, "type": "unusual_authentication", "evidence": {"failed_count": len(recent_failed)}, "confidence": 0.6})
            elif is_anom:
                out.append({"event": e, "type": "unusual_authentication", "evidence": meta, "confidence": 0.8})
    return out

def detect_unusual_api(events: list[dict], tenant: str) -> list[dict]:
    # frequency of API actions per actor
    counter = Counter(f"{e.get('actor')}:{e.get('action')}" for e in events if e.get("tenant")==tenant and e.get("category") in {"APPLICATION","NETWORK"})
    out=[]
    for key, cnt in counter.items():
        if cnt >= 20:  # burst
            out.append({"key": key, "type": "unusual_api_usage", "count": cnt, "confidence": 0.7})
    return out

def detect_unusual_data_access(events: list[dict], tenant: str) -> list[dict]:
    out=[]
    for e in events:
        if e.get("tenant")!=tenant or e.get("category")!="DATA":
            continue
        # restricted data access anomaly
        meta = e.get("source_metadata", {})
        classification = meta.get("classification") or e.get("data_classification") or ""
        if classification in {"RESTRICTED","SECRET","CONFIDENTIAL"}:
            # record baseline per actor
            baseline_store.record(tenant, "DATA", e.get("actor",""), "access_restricted", 1.0)
            is_anom,_ = baseline_store.is_anomalous(tenant, "DATA", e.get("actor",""), "access_restricted", 1.0)
            # heuristic: if actor accesses >3 restricted in window, flag
            restricted = [x for x in events if x.get("actor")==e.get("actor") and (x.get("source_metadata",{}).get("classification") in {"RESTRICTED","SECRET"})]
            if len(restricted) >= 3:
                out.append({"event": e, "type": "unusual_data_access", "count": len(restricted), "confidence": 0.65})
    return out

def detect_unusual_agent(events: list[dict], tenant: str) -> list[dict]:
    out=[]
    for e in events:
        if e.get("tenant")!=tenant or e.get("category")!="AGENT":
            continue
        # excessive tool calls
        tool = e.get("source_metadata",{}).get("tool") or e.get("action")
        baseline_store.record(tenant, "AGENT", e.get("actor",""), tool or "tool_call", 1.0)
        agent_events = [x for x in events if x.get("actor")==e.get("actor") and x.get("category")=="AGENT"]
        if len(agent_events) >= 10:
            out.append({"event": e, "type": "unusual_agent_activity", "count": len(agent_events), "confidence": 0.6})
    return out

def detect_unusual_deployment(events: list[dict], tenant: str) -> list[dict]:
    out=[]
    for e in events:
        if e.get("tenant")!=tenant: continue
        if e.get("source")=="deployment" or e.get("category")=="CONFIGURATION":
            if "unexpected" in e.get("action","").lower() or e.get("source_metadata",{}).get("unexpected"):
                out.append({"event": e, "type": "unusual_deployment_activity", "confidence": 0.75})
    return out

def detect_unusual_network(events: list[dict], tenant: str) -> list[dict]:
    out=[]
    ip_counter = Counter(e.get("ip") for e in events if e.get("tenant")==tenant and e.get("ip"))
    for ip,cnt in ip_counter.items():
        if cnt >= 15 and ip:
            out.append({"ip": ip, "type": "unusual_network_activity", "count": cnt, "confidence": 0.6})
    return out

def detect_all(events: list[dict], tenant: str) -> list[dict]:
    results=[]
    results.extend(detect_unusual_auth(events, tenant))
    results.extend(detect_unusual_api(events, tenant))
    results.extend(detect_unusual_data_access(events, tenant))
    results.extend(detect_unusual_agent(events, tenant))
    results.extend(detect_unusual_deployment(events, tenant))
    results.extend(detect_unusual_network(events, tenant))
    return results
