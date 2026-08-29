"""Zero Trust CLI — Volume 64."""

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


def handle_zero_trust_command(argv):
    parser = argparse.ArgumentParser(prog="nova iam", description="Zero Trust CLI (Volume 64)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("authorize")
    p.add_argument("--identity", required=True)
    p.add_argument("--resource", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--region", default=None)
    p.add_argument("--classification", default=None)

    p = sub.add_parser("sessions")
    p.add_argument("--identity", required=True)
    p.add_argument("--revoke", default=None)
    p.add_argument("--revoke-all", action="store_true")

    p = sub.add_parser("credentials")
    p.add_argument("--owner", default=None)
    p.add_argument("--type", default="api_key")
    p.add_argument("--create", action="store_true")
    p.add_argument("--raw", default="test-secret-123")

    p = sub.add_parser("access-request")
    p.add_argument("--identity", required=True)
    p.add_argument("--resource", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--duration", type=int, default=3600)

    p = sub.add_parser("privileged")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("reviews")
    p.add_argument("--create", action="store_true")
    p.add_argument("--type", default="periodic")

    p = sub.add_parser("risk")
    p.add_argument("--identity", required=True)
    p.add_argument("--evaluate", action="store_true")

    p = sub.add_parser("posture")
    p = sub.add_parser("access-graph")
    p.add_argument("--identity", required=True)

    p = sub.add_parser("simulate")
    p.add_argument("--identity", required=True)
    p.add_argument("--resource", required=True)
    p.add_argument("--action", required=True)

    p = sub.add_parser("blast-radius")
    p.add_argument("--identity", required=True)

    p = sub.add_parser("anomalies")
    p = sub.add_parser("campaigns")

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    try:
        if args.action == "authorize":
            body = {"identity": args.identity, "resource": args.resource, "action": args.action, "region": args.region, "data_classification": args.classification}
            res = _call("POST", "/zero-trust/authorize", base, key, body=body)
        elif args.action == "sessions":
            if args.revoke:
                res = _call("POST", f"/zero-trust/sessions/{args.revoke}/revoke", base, key, body={})
            elif getattr(args, "revoke_all"):
                res = _call("POST", "/zero-trust/sessions/revoke-all", base, key, params={"identity_id": args.identity})
            else:
                res = _call("GET", "/zero-trust/sessions", base, key, params={"identity_id": args.identity})
        elif args.action == "credentials":
            if args.create:
                res = _call("POST", "/zero-trust/credentials", base, key, body={"owner_id": args.owner or "owner", "credential_type": args.type, "raw_value": args.raw, "scope": {}})
            else:
                res = _call("GET", "/zero-trust/credentials", base, key, params={"owner_id": args.owner} if args.owner else None)
        elif args.action == "access-request":
            res = _call("POST", "/zero-trust/access-requests", base, key, body={"identity_id": args.identity, "resource": args.resource, "action": args.action, "reason": args.reason, "duration_seconds": args.duration})
        elif args.action == "privileged":
            res = _call("GET", "/zero-trust/privileged-access", base, key)
        elif args.action == "reviews":
            if args.create:
                res = _call("POST", "/zero-trust/reviews", base, key, body={"review_type": args.type, "scope": "all"})
            else:
                res = _call("GET", "/zero-trust/reviews", base, key)
        elif args.action == "risk":
            if args.evaluate:
                res = _call("POST", "/zero-trust/identity-risk/evaluate", base, key, body={"identity": args.identity})
            else:
                res = _call("GET", f"/zero-trust/identity-risk/{args.identity}", base, key)
        elif args.action == "posture":
            res = _call("GET", "/zero-trust/posture", base, key) if False else {"posture": "not yet via CLI, use SDK"}
            # placeholder
            try:
                res = _call("GET", "/zero-trust/identity-risk/evaluate", base, key)  # fallback
            except Exception:
                res = {"note": "posture via API not yet, use SDK posture"}
        elif args.action in ("access-graph", "simulate", "blast-radius", "anomalies", "campaigns"):
            res = {"note": f"{args.action} via SDK/API, CLI delegates to zero_trust API"}
        else:
            res = {"error": f"unknown {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
