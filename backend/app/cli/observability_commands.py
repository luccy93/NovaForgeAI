"""Observability CLI — Volume 59 Commit 1 + Commit 2.

``nova observe services|health|metrics|logs|traces|alerts|slo|map`` with --json.
``nova aiops anomalies|incident|root-cause|recommend|remediate|forecast|health`` with --json.
Additive: keeps all Commit 1 commands, adds AIOps subcommands reusing platform/aiops/remediation services via API.
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
    # Delegate to aiops if first arg is aiops
    if argv and argv[0] == "aiops":
        return handle_aiops_command(argv[1:])
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
    # Commit 2: also allow AIOps subcommands via observe aiops wrapper (additive)
    # We keep parser separate; handle_aiops_command is the canonical entry
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


def handle_aiops_command(argv):
    """Handle ``nova aiops`` subcommands: anomalies, incident, root-cause, recommend, remediate, forecast, health."""
    parser = argparse.ArgumentParser(prog="nova aiops", description="AIOps CLI — anomalies, incident, root-cause, recommend, remediate, forecast, health")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    # anomalies: list or detect
    p = sub.add_parser("anomalies", help="List anomalies or detect (use --detect)")
    p.add_argument("--metric", default=None, help="metric name filter")
    p.add_argument("--window-hours", type=int, default=24)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--detect", action="store_true", help="POST /anomalies/detect instead of GET")
    p.add_argument("--window", type=int, default=None, help="alias for --window-hours")

    # incident: summary
    p = sub.add_parser("incident", help="Incident summary")
    p.add_argument("incident_id", help="incident id")
    p.add_argument("--summary", action="store_true", help="explicit summary (default)")

    # root-cause
    p = sub.add_parser("root-cause", help="Root cause analysis")
    p.add_argument("incident_id", help="incident id")

    # recommend
    p = sub.add_parser("recommend", help="List or approve recommendations")
    p.add_argument("--category", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--approve", default=None, help="recommendation id to approve")
    p.add_argument("--approver", default=None)

    # remediate: request | approve | execute
    p = sub.add_parser("remediate", help="Remediation lifecycle")
    p.add_argument("--incident-id", default=None)
    p.add_argument("--action", default=None, help="action for request, e.g., restart_service")
    p.add_argument("--scope", default=None, help="JSON scope dict for request")
    p.add_argument("--request-id", default=None, help="remediation request id for approve/execute")
    p.add_argument("--approve", action="store_true", help="approve remediation")
    p.add_argument("--execute", action="store_true", help="execute remediation")
    p.add_argument("--approver", default=None)
    p.add_argument("--actor", default=None)

    # forecast: capacity or cost
    p = sub.add_parser("forecast", help="Capacity or cost forecast")
    p.add_argument("--service", default="")
    p.add_argument("--horizon-hours", type=int, default=24)
    p.add_argument("--metric", default="")
    p.add_argument("--cost", action="store_true", help="show cost anomalies instead of capacity")
    p.add_argument("--window-hours", type=int, default=24)
    p.add_argument("--sensitivity", type=float, default=2.0)

    # health: observability quality + aiops status
    p = sub.add_parser("health", help="Observability quality and AIOps status")
    p.add_argument("--service", default="")
    p.add_argument("--quality", action="store_true", help="only quality")
    p.add_argument("--status", action="store_true", help="only aiops status")

    args = parser.parse_args(argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(args.as_json)
    try:
        res: dict = {}
        if args.action == "anomalies":
            wh = args.window if args.window is not None else args.__dict__.get("window_hours", 24)
            if args.detect:
                res = _call("POST", "/observability/anomalies/detect", base, key, body={"metric": args.metric or "", "window_hours": wh})
            else:
                params = {"window_hours": wh, "limit": args.limit}
                if args.metric:
                    params["metric"] = args.metric
                res = _call("GET", "/observability/anomalies", base, key, params=params)
        elif args.action == "incident":
            res = _call("GET", f"/observability/incidents/{args.incident_id}/summary", base, key)
        elif args.action == "root-cause":
            res = _call("POST", f"/observability/root-cause/{args.incident_id}", base, key, body={})
        elif args.action == "recommend":
            if args.approve:
                res = _call("POST", f"/observability/recommendations/{args.approve}/approve", base, key, body={"approver": args.approver or "cli"})
            else:
                params = {"limit": args.limit}
                if args.category:
                    params["category"] = args.category
                res = _call("GET", "/observability/recommendations", base, key, params=params)
        elif args.action == "remediate":
            if args.approve and args.request_id:
                res = _call("POST", f"/observability/remediation/{args.request_id}/approve", base, key, body={"approver": args.approver or "cli"})
            elif args.execute and args.request_id:
                res = _call("POST", f"/observability/remediation/{args.request_id}/execute", base, key, body={"actor": args.actor or args.approver or "cli"})
            elif args.incident_id and args.action:
                scope = {}
                if args.scope:
                    try:
                        scope = json.loads(args.scope)
                    except Exception:
                        scope = {"raw": args.scope}
                res = _call("POST", "/observability/remediation/request", base, key, body={"incident_id": args.incident_id, "action": args.action, "scope": scope})
            else:
                parser.print_help(file=sys.stderr)
                sys.exit(2)
        elif args.action == "forecast":
            if args.cost:
                res = _call("GET", "/observability/forecast/cost", base, key, params={"window_hours": args.window_hours, "sensitivity": args.sensitivity})
            else:
                params = {"horizon_hours": args.__dict__.get("horizon_hours", 24)}
                if args.service:
                    params["service"] = args.service
                if args.metric:
                    params["metric"] = args.metric
                res = _call("GET", "/observability/forecast/capacity", base, key, params=params)
        elif args.action == "health":
            if args.quality and not args.status:
                res = _call("GET", "/observability/observability-quality", base, key, params={"service": args.service} if args.service else {})
            elif args.status and not args.quality:
                res = _call("GET", "/observability/aiops/status", base, key)
            else:
                # both
                q = _call("GET", "/observability/observability-quality", base, key, params={"service": args.service} if args.service else {})
                s = _call("GET", "/observability/aiops/status", base, key)
                res = {"quality": q, "aiops_status": s}
        else:
            res = {"error": f"unknown {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
