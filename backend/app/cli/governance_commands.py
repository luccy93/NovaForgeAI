"""Governance CLI commands — Volume 71 Commit 1.

Thin HTTP client over /api/v1/governance following the domain CLI
pattern (argparse subcommands, --json flag, Bearer auth).
"""

import argparse
import json
import os
import sys

import httpx


def _base(explicit=None) -> str:
    return explicit or os.environ.get("NOVAFORGE_BASE_URL", "http://localhost:8000")


def _key(explicit=None) -> str:
    return explicit or os.environ.get("NOVAFORGE_API_KEY", "") or os.environ.get("API_KEY", "")


def _call(method, path, base, key, body=None, params=None) -> dict:
    url = f"{base}/api/v1{path}"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    with httpx.Client(timeout=30.0) as client:
        resp = client.request(method, url, headers=headers, json=body, params=params)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed ({resp.status_code}): {resp.text[:500]}")
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def _out(data, as_json: bool) -> None:
    print(json.dumps(data, indent=2, default=str))


def handle_governance_command(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    parser = argparse.ArgumentParser(prog="nova governance")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("policies")
    p_create = sub.add_parser("create-policy")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--domain", default="general")
    p_eval = sub.add_parser("evaluate")
    p_eval.add_argument("--scope-type", default="tenant")
    p_eval.add_argument("--scope-value", default="")
    p_eval.add_argument("--operation", default="")
    p_sim = sub.add_parser("simulate")
    p_sim.add_argument("--scope-type", default="tenant")
    p_sim.add_argument("--operation", default="")
    sub.add_parser("decisions")
    sub.add_parser("exceptions")
    sub.add_parser("posture")
    sub.add_parser("controls")
    sub.add_parser("evidence")
    sub.add_parser("drift")
    p_report = sub.add_parser("report")
    p_report.add_argument("--type", default="posture")
    p_explain = sub.add_parser("explain")
    p_explain.add_argument("--decision-id", required=True)

    args = parser.parse_args(argv)
    base, key = _base(args.base_url), _key(args.api_key)
    if args.cmd == "policies":
        _out(_call("GET", "/governance/policies", base, key), as_json)
    elif args.cmd == "create-policy":
        _out(_call("POST", "/governance/policies", base, key,
                   body={"name": args.name, "domain": args.domain}), as_json)
    elif args.cmd == "evaluate":
        _out(_call("POST", "/governance/evaluate", base, key, body={
            "scope_type": args.scope_type, "scope_value": args.scope_value,
            "operation": args.operation, "context": {}}), as_json)
    elif args.cmd == "simulate":
        _out(_call("POST", "/governance/simulate", base, key, body={
            "scope_type": args.scope_type, "operation": args.operation,
            "context": {}}), as_json)
    elif args.cmd == "decisions":
        _out(_call("GET", "/governance/decisions", base, key), as_json)
    elif args.cmd == "exceptions":
        _out(_call("GET", "/governance/policy-exceptions", base, key), as_json)
    elif args.cmd == "posture":
        _out(_call("GET", "/governance/posture", base, key), as_json)
    elif args.cmd == "controls":
        _out(_call("GET", "/governance/controls", base, key), as_json)
    elif args.cmd == "evidence":
        _out(_call("GET", "/governance/evidence/coverage", base, key), as_json)
    elif args.cmd == "drift":
        _out(_call("GET", "/governance/drift", base, key), as_json)
    elif args.cmd == "report":
        _out(_call("POST", "/governance/reports", base, key,
                   body={"report_type": args.type}), as_json)
    elif args.cmd == "explain":
        _out(_call("GET", f"/governance/decisions/{args.decision_id}/explain",
                   base, key), as_json)
    else:
        parser.print_help()
