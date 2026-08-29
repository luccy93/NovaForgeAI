"""Event correlation — Volume 63.

Correlate using actor/resource/tenant/region/trace/request/time_window/deployment/IP.
Do not infer identity from weak signals — only strong actor binding (user_id/service_account).
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


STRONG_ACTOR_FIELDS = {"actor", "actor_id", "user_id", "service_account"}
CORRELATION_KEYS = {"actor", "resource", "tenant", "region", "trace_id", "request_id", "deployment_id", "ip"}


def _parse_ts(ts: str) -> datetime:
    try:
        # handle iso with Z
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now(timezone.utc)


def correlate_events(events: list[dict], time_window_seconds: int = 300) -> list[dict]:
    """Group events into correlation buckets.

    Returns list of groups: {key, key_type, events, tenant, earliest, latest}
    Groups by each strong key; events correlated if share any key + within window.
    """
    if not events:
        return []

    # Buckets: key_type -> value -> list[events]
    by_actor: dict[str, list[dict]] = defaultdict(list)
    by_resource: dict[str, list[dict]] = defaultdict(list)
    by_tenant: dict[str, list[dict]] = defaultdict(list)
    by_region: dict[str, list[dict]] = defaultdict(list)
    by_trace: dict[str, list[dict]] = defaultdict(list)
    by_request: dict[str, list[dict]] = defaultdict(list)
    by_deployment: dict[str, list[dict]] = defaultdict(list)
    by_ip: dict[str, list[dict]] = defaultdict(list)

    for e in events:
        if e.get("actor"):
            by_actor[e["actor"]].append(e)
        if e.get("resource"):
            by_resource[e["resource"]].append(e)
        if e.get("tenant"):
            by_tenant[e["tenant"]].append(e)
        if e.get("region"):
            by_region[e["region"]].append(e)
        if e.get("trace_id"):
            by_trace[e["trace_id"]].append(e)
        if e.get("request_id"):
            by_request[e["request_id"]].append(e)
        if e.get("deployment_id"):
            by_deployment[e["deployment_id"]].append(e)
        if e.get("ip"):
            by_ip[e["ip"]].append(e)

    groups: list[dict] = []

    def _add_groups(mapping: dict, key_type: str):
        for val, evs in mapping.items():
            if len(evs) < 2:
                continue
            # check time window: sort by timestamp
            sorted_evs = sorted(evs, key=lambda x: _parse_ts(x.get("timestamp", "")))
            # split if gap > window
            cluster: list[dict] = [sorted_evs[0]]
            for ev in sorted_evs[1:]:
                prev_ts = _parse_ts(cluster[-1].get("timestamp", ""))
                cur_ts = _parse_ts(ev.get("timestamp", ""))
                if (cur_ts - prev_ts).total_seconds() <= time_window_seconds:
                    cluster.append(ev)
                else:
                    if len(cluster) >= 2:
                        groups.append({
                            "key": val,
                            "key_type": key_type,
                            "events": cluster.copy(),
                            "tenant": cluster[0].get("tenant"),
                            "earliest": cluster[0].get("timestamp"),
                            "latest": cluster[-1].get("timestamp"),
                            "count": len(cluster),
                        })
                    cluster = [ev]
            if len(cluster) >= 2:
                groups.append({
                    "key": val,
                    "key_type": key_type,
                    "events": cluster,
                    "tenant": cluster[0].get("tenant"),
                    "earliest": cluster[0].get("timestamp"),
                    "latest": cluster[-1].get("timestamp"),
                    "count": len(cluster),
                })

    _add_groups(by_actor, "actor")
    _add_groups(by_resource, "resource")
    _add_groups(by_trace, "trace")
    _add_groups(by_request, "request")
    _add_groups(by_deployment, "deployment")
    _add_groups(by_ip, "ip")
    # tenant/region alone are weak for grouping - only if combined with time window already
    # we include them but require >=3 events to avoid noisy tenant grouping
    for val, evs in by_tenant.items():
        if len(evs) >= 3:
            sorted_evs = sorted(evs, key=lambda x: _parse_ts(x.get("timestamp", "")))
            groups.append({"key": val, "key_type": "tenant", "events": sorted_evs, "tenant": val, "count": len(sorted_evs), "earliest": sorted_evs[0].get("timestamp"), "latest": sorted_evs[-1].get("timestamp")})

    return groups


def filter_by_tenant(events: list[dict], tenant: str) -> list[dict]:
    return [e for e in events if e.get("tenant") == tenant]
