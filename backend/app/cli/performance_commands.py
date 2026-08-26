"""Performance CLI — Volume 61 Commit 1.

``nova perf services|endpoints|database|queues|ai|capacity --json`` calling
API via httpx at {base}/api/v1/performance/... with proper params/body.

Additive, no placeholders, reuses app.performance.* via API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def _base(explicit=None) -> str:
    return (explicit or os.environ.get("NOVAFORGE_BASE_URL") or "http://localhost:8000").rstrip("/")


def _key(explicit=None):
    return explicit or os.environ.get("NOVAFORGE_API_KEY") or os.environ.get("API_KEY")


def _headers(k):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if k:
        h["Authorization"] = f"Bearer {k}"
    return h


def _call(method: str, path: str, base: str, key, body=None, params=None):
    url = f"{base}/api/v1{path}"
    headers = _headers(key)
    with httpx.Client(timeout=20) as client:
        resp = client.request(method, url, headers=headers, json=body, params=params)
        # raise for status with detail
        if resp.status_code >= 400:
            # include body for debugging but still raise
            try:
                detail = resp.text[:500]
            except Exception:
                detail = str(resp.status_code)
            raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
        return resp.json() if resp.content else {}


def handle_performance_command(argv):
    """Handle ``nova perf`` subcommands: services, endpoints, database, queues, ai, capacity.

    Also supports additive budgets/metrics/scaling subcommands for completeness.
    """
    parser = argparse.ArgumentParser(prog="nova perf", description="Performance CLI — Volume 61")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="action", required=True)

    # services: GET /performance/services/{service}/metrics
    p = sub.add_parser("services", help="Service metrics (request_rate/latency/error/saturation)")
    p.add_argument("--service", default=None, help="service name (default api)")
    p.add_argument("service_pos", nargs="?", default=None, help="positional service name")
    p.add_argument("--metric", default=None, help="metric_name filter")
    p.add_argument("--metric-name", default=None, help="alias for --metric")
    p.add_argument("--granularity", default=None, help="minute|hour|day|week|month")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--start-time", default=None)
    p.add_argument("--end-time", default=None)
    p.add_argument("--from", dest="from_time", default=None)
    p.add_argument("--to", dest="to_time", default=None)
    p.add_argument("--timeout", type=int, default=5)

    # endpoints: GET /performance/endpoints/metrics
    p = sub.add_parser("endpoints", help="Endpoint metrics (route/method/status/latency)")
    p.add_argument("--route", default=None)
    p.add_argument("--method", default=None)
    p.add_argument("--service", default="api")
    p.add_argument("--status", default=None)
    p.add_argument("--granularity", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--start-time", default=None)
    p.add_argument("--end-time", default=None)
    p.add_argument("--timeout", type=int, default=5)

    # database: GET /performance/database/metrics
    p = sub.add_parser("database", help="Database metrics (pool/slow queries/index recommendations)")
    p.add_argument("--threshold-ms", type=float, default=500, help="slow query threshold ms")
    p.add_argument("--threshold", type=float, default=None, help="alias for --threshold-ms")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--timeout", type=int, default=5)

    # queues: GET /performance/queues/metrics
    p = sub.add_parser("queues", help="Queue metrics (depth/lag/processing_rate/backpressure)")
    p.add_argument("--queue", default=None, help="queue name")
    p.add_argument("--queue-name", default=None, help="alias for --queue")
    p.add_argument("queue_pos", nargs="?", default=None, help="positional queue name")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--timeout", type=int, default=5)

    # ai: GET /performance/services/ai/metrics (or query)
    p = sub.add_parser("ai", help="AI metrics (tokens/latency/model)")
    p.add_argument("--service", default="ai", help="ai service name")
    p.add_argument("service_pos", nargs="?", default=None)
    p.add_argument("--metric", default=None)
    p.add_argument("--metric-name", default=None)
    p.add_argument("--granularity", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--start-time", default=None)
    p.add_argument("--end-time", default=None)
    p.add_argument("--timeout", type=int, default=5)

    # capacity: GET /performance/capacity
    p = sub.add_parser("capacity", help="Capacity pools/policies/snapshots")
    p.add_argument("--resource", default=None)
    p.add_argument("--pool-type", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--timeout", type=int, default=5)

    # additive: budgets
    p = sub.add_parser("budgets", help="List budgets")
    p.add_argument("--service", default=None)
    p.add_argument("--metric-type", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)

    # additive: recommendations
    p = sub.add_parser("recommendations", help="List recommendations")
    p.add_argument("--type", dest="rec_type", default=None)
    p.add_argument("--status", default=None)
    p.add_argument("--resource", default=None)
    p.add_argument("--limit", type=int, default=50)

    # additive: scaling-events
    p = sub.add_parser("scaling-events", help="List scaling events")
    p.add_argument("--resource", default=None)
    p.add_argument("--direction", default=None)
    p.add_argument("--limit", type=int, default=100)

    # raw argv handling for --json placed anywhere (like resilience)
    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    # filter --json for parsing but keep as_json flag
    filtered_argv = [a for a in raw_argv if a != "--json"]
    # Also handle `--json` as dest; argparse will set as_json even if filtered, so we handle manually
    try:
        args = parser.parse_args(filtered_argv)
    except SystemExit:
        raise

    base = _base(getattr(args, "base_url", None))
    key = _key(getattr(args, "api_key", None))
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    try:
        res: Any = {}
        action = getattr(args, "action", None)

        if action == "services":
            # resolve service name: --service > positional > default api
            svc = getattr(args, "service", None) or getattr(args, "service_pos", None) or "api"
            # if positional was used as --service alias, service_pos may contain it; if action was called as `nova perf services myservice`, service_pos will be myservice
            params: dict[str, Any] = {"limit": getattr(args, "limit", 100), "timeout": getattr(args, "timeout", 5)}
            mn = getattr(args, "metric", None) or getattr(args, "metric_name", None)
            if mn:
                params["metric_name"] = mn
            if getattr(args, "granularity", None):
                params["granularity"] = getattr(args, "granularity", None)
            if getattr(args, "start_time", None):
                params["start_time"] = getattr(args, "start_time", None)
            if getattr(args, "end_time", None):
                params["end_time"] = getattr(args, "end_time", None)
            ft = getattr(args, "from_time", None)
            tt = getattr(args, "to_time", None)
            if ft:
                params["from"] = ft
            if tt:
                params["to"] = tt
            res = _call("GET", f"/performance/services/{svc}/metrics", base, key, params=params)

        elif action == "endpoints":
            params = {"limit": getattr(args, "limit", 100), "service": getattr(args, "service", "api"), "timeout": getattr(args, "timeout", 5)}
            if getattr(args, "route", None):
                params["route"] = getattr(args, "route")
            if getattr(args, "method", None):
                params["method"] = getattr(args, "method")
            if getattr(args, "status", None) is not None:
                params["status"] = getattr(args, "status")
            if getattr(args, "granularity", None):
                params["granularity"] = getattr(args, "granularity")
            if getattr(args, "start_time", None):
                params["start_time"] = getattr(args, "start_time")
            if getattr(args, "end_time", None):
                params["end_time"] = getattr(args, "end_time")
            # strip empty service timeout handling: ensure service present
            res = _call("GET", "/performance/endpoints/metrics", base, key, params=params)

        elif action == "database":
            thr = getattr(args, "threshold_ms", 500)
            thr_alias = getattr(args, "threshold", None)
            if thr_alias is not None:
                thr = thr_alias
            params = {"threshold_ms": float(thr), "limit": getattr(args, "limit", 20), "offset": getattr(args, "offset", 0), "timeout": getattr(args, "timeout", 5)}
            res = _call("GET", "/performance/database/metrics", base, key, params=params)

        elif action == "queues":
            qname = getattr(args, "queue", None) or getattr(args, "queue_name", None) or getattr(args, "queue_pos", None)
            params: dict[str, Any] = {"limit": getattr(args, "limit", 100), "timeout": getattr(args, "timeout", 5)}
            if qname:
                params["queue_name"] = qname
                params["queue"] = qname
            res = _call("GET", "/performance/queues/metrics", base, key, params=params)

        elif action == "ai":
            svc = getattr(args, "service", "ai") or getattr(args, "service_pos", None) or "ai"
            # positional override if service_pos provided
            pos = getattr(args, "service_pos", None)
            if pos:
                svc = pos
            params = {"limit": getattr(args, "limit", 100), "timeout": getattr(args, "timeout", 5)}
            mn = getattr(args, "metric", None) or getattr(args, "metric_name", None)
            if mn:
                params["metric_name"] = mn
            if getattr(args, "granularity", None):
                params["granularity"] = getattr(args, "granularity")
            if getattr(args, "start_time", None):
                params["start_time"] = getattr(args, "start_time")
            if getattr(args, "end_time", None):
                params["end_time"] = getattr(args, "end_time")
            res = _call("GET", f"/performance/services/{svc}/metrics", base, key, params=params)

        elif action == "capacity":
            params = {"limit": getattr(args, "limit", 100), "offset": getattr(args, "offset", 0), "timeout": getattr(args, "timeout", 5)}
            if getattr(args, "resource", None):
                params["resource"] = getattr(args, "resource")
            if getattr(args, "pool_type", None):
                params["pool_type"] = getattr(args, "pool_type")
            res = _call("GET", "/performance/capacity", base, key, params=params)

        elif action == "budgets":
            params = {"limit": getattr(args, "limit", 100), "offset": getattr(args, "offset", 0)}
            if getattr(args, "service", None):
                params["service"] = getattr(args, "service")
            mt = getattr(args, "metric_type", None)
            if mt:
                params["metric_type"] = mt
            res = _call("GET", "/performance/budgets", base, key, params=params)

        elif action == "recommendations":
            params = {"limit": getattr(args, "limit", 50)}
            rt = getattr(args, "rec_type", None)
            if rt:
                params["type"] = rt
            if getattr(args, "status", None):
                params["status"] = getattr(args, "status")
            if getattr(args, "resource", None):
                params["resource"] = getattr(args, "resource")
            res = _call("GET", "/performance/recommendations", base, key, params=params)

        elif action == "scaling-events":
            params = {"limit": getattr(args, "limit", 100)}
            if getattr(args, "resource", None):
                params["resource"] = getattr(args, "resource")
            if getattr(args, "direction", None):
                params["direction"] = getattr(args, "direction")
            res = _call("GET", "/performance/scaling-events", base, key, params=params)

        else:
            res = {"error": f"unknown action {action}"}

        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
