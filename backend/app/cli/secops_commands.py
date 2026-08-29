"""SecOps CLI — Volume 63 Commit 1.

nova security events|alerts|findings|cases|investigate|indicators|risk --json
"""

import argparse
import json
import os
import sys

import httpx


def _base(explicit=None):
    return (explicit or os.environ.get("NOVAFORGE_BASE_URL") or "http://localhost:8000").rstrip("/")


def _key(explicit=None):
    return explicit or os.environ.get("NOVAFORGE_API_KEY") or os.environ.get("API_KEY")


def _call(method, path, base, key, body=None, params=None):
    url = f"{base}/api/v1{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with httpx.Client(timeout=30) as client:
        resp = client.request(method, url, headers=headers, json=body, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}


def handle_secops_command(argv):
    parser = argparse.ArgumentParser(prog="nova security", description="Security Operations CLI (Volume 63)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("events")
    p.add_argument("--source", default="unknown")
    p.add_argument("--resource", default="")
    p.add_argument("--actor", default="")
    p.add_argument("--action", default="")
    p.add_argument("--category", default=None)
    p.add_argument("--severity", default="INFO")
    p.add_argument("--ingest", action="store_true")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("alerts")
    p.add_argument("--status", default=None)
    p.add_argument("--severity", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--id", default=None)
    p.add_argument("--acknowledge", default=None)
    p.add_argument("--resolve", default=None)

    p = sub.add_parser("findings")
    p.add_argument("--finding", default=None)
    p.add_argument("--resource", default=None)
    p.add_argument("--severity", default="MEDIUM")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("cases")
    p.add_argument("--title", default=None)
    p.add_argument("--severity", default="MEDIUM")
    p.add_argument("--status", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--id", default=None)

    p = sub.add_parser("investigate")
    p.add_argument("target_id")

    p = sub.add_parser("indicators")
    p.add_argument("--indicator", default=None)
    p.add_argument("--type", default="IP")
    p.add_argument("--source", default="manual")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("risk")
    p.add_argument("--resource", default="")
    p.add_argument("--severity", default="MEDIUM")
    p.add_argument("--calculate", action="store_true")

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    try:
        if args.action == "events":
            if args.ingest:
                body = {"source": args.source, "resource": args.resource, "actor": args.actor, "action": args.action, "category": args.category or "APPLICATION", "severity": args.severity}
                res = _call("POST", "/secops/security-events", base, key, body=body)
            else:
                params = {"limit": args.limit}
                if args.category:
                    params["category"] = args.category
                if args.severity:
                    params["severity"] = args.severity
                res = _call("GET", "/secops/security-events", base, key, params=params)
        elif args.action == "alerts":
            if args.id:
                res = _call("GET", f"/secops/security-alerts/{args.id}", base, key)
            elif args.acknowledge:
                res = _call("POST", f"/secops/security-alerts/{args.acknowledge}/acknowledge", base, key, body={})
            elif args.resolve:
                res = _call("POST", f"/secops/security-alerts/{args.resolve}/status", base, key, body={"status": "RESOLVED"})
            else:
                params = {"limit": args.limit}
                if args.status:
                    params["status"] = args.status
                if args.severity:
                    params["severity"] = args.severity
                res = _call("GET", "/secops/security-alerts", base, key, params=params)
        elif args.action == "findings":
            if args.finding:
                res = _call("POST", "/secops/findings", base, key, body={"finding": args.finding, "resource": args.resource or "unknown", "severity": args.severity})
            else:
                res = _call("GET", "/secops/findings", base, key, params={"limit": args.limit})
        elif args.action == "cases":
            if args.title:
                res = _call("POST", "/secops/cases", base, key, body={"title": args.title, "severity": args.severity})
            elif args.id:
                res = _call("GET", f"/secops/cases/{args.id}", base, key)
            else:
                params = {"limit": args.limit}
                if args.status:
                    params["status"] = args.status
                res = _call("GET", "/secops/cases", base, key, params=params)
        elif args.action == "investigate":
            res = _call("GET", f"/secops/investigations/{args.target_id}", base, key)
        elif args.action == "indicators":
            if args.indicator:
                res = _call("POST", "/secops/indicators", base, key, body={"indicator": args.indicator, "indicator_type": args.type, "source": args.source})
            else:
                res = _call("GET", "/secops/indicators", base, key, params={"limit": args.limit})
        elif args.action == "risk":
            if args.calculate:
                res = _call("POST", "/secops/risk/calculate", base, key, body={"resource": args.resource, "severity": args.severity})
            else:
                res = _call("GET", "/secops/risk", base, key)
        else:
            res = {"error": f"unknown action {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
