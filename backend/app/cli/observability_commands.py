"""Observability CLI — Volume 59 Commit 1.

``nova observe services|health|metrics|logs|traces|alerts|slo|map`` with --json.
"""

import argparse, json, os, sys
import httpx

def _base(explicit=None):
    return (explicit or os.environ.get("NOVAFORGE_BASE_URL") or "http://localhost:8000").rstrip("/")

def _key(explicit=None):
    return explicit or os.environ.get("NOVAFORGE_API_KEY") or os.environ.get("API_KEY")

def _headers(k):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if k:
        h["Authorization"] = f"Bearer {k}"
    return h

def _call(method, path, base, key, body=None, params=None):
    url = f"{base}/api/v1{path}"
    with httpx.Client(timeout=20) as client:
        resp = client.request(method, url, headers=_headers(key), json=body, params=params)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

def handle_observability_command(argv):
    parser = argparse.ArgumentParser(prog="nova observe", description="Observability CLI")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("services")
    p = sub.add_parser("health"); p.add_argument("resource"); p.add_argument("--check-type", default="readiness")
    p = sub.add_parser("metrics"); p.add_argument("--metric", required=True); p.add_argument("--type", default="gauge"); p.add_argument("--value", type=float, required=True)
    p = sub.add_parser("logs"); p.add_argument("--service", required=True); p.add_argument("--level", default="INFO"); p.add_argument("--message", required=True)
    p = sub.add_parser("traces"); p.add_argument("--trace-id", required=True); p.add_argument("--span-id", required=True); p.add_argument("--service", required=True); p.add_argument("--operation", required=True)
    sub.add_parser("alerts")
    p = sub.add_parser("slo"); p.add_argument("--service", required=True); p.add_argument("--indicator", required=True); p.add_argument("--target", type=float, required=True)
    sub.add_parser("map")
    args = parser.parse_args(argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(args.as_json)
    try:
        if args.action == "services":
            res = _call("GET", "/observability/services", base, key)
        elif args.action == "health":
            res = _call("GET", f"/observability/health/{args.resource}", base, key, params={"check_type": args.check_type})
        elif args.action == "metrics":
            res = _call("POST", "/observability/metrics", base, key, body={"metric": args.metric, "type": args.type, "value": args.value})
        elif args.action == "logs":
            res = _call("POST", "/observability/logs", base, key, body={"service": args.service, "level": args.level, "message": args.message, "environment": "production"})
        elif args.action == "traces":
            res = _call("POST", "/observability/traces", base, key, body={"trace_id": args.trace_id, "span_id": args.span_id, "service": args.service, "operation": args.operation, "duration_ms": 100, "status": "ok"})
        elif args.action == "alerts":
            res = _call("GET", "/observability/alerts", base, key)
        elif args.action == "slo":
            res = _call("POST", "/observability/slos", base, key, body={"service": args.service, "indicator": args.indicator, "target": args.target, "window": "30d"})
        elif args.action == "map":
            res = _call("GET", "/observability/service-map", base, key)
        else:
            res = {"error": f"unknown {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
