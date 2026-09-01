"""Workflow CLI — Volume 66."""

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


def handle_workflow_command(argv):
    parser = argparse.ArgumentParser(prog="nova workflow", description="Workflow CLI (Volume 66)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("list")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--status", default=None)

    p = sub.add_parser("get")
    p.add_argument("workflow_id")

    p = sub.add_parser("publish")
    p.add_argument("workflow_id")
    p.add_argument("--version-id", default=None)

    p = sub.add_parser("run")
    p.add_argument("workflow_id")
    p.add_argument("--inputs", default="{}")
    p.add_argument("--idempotency-key", default=None)

    p = sub.add_parser("status")
    p.add_argument("run_id")

    p = sub.add_parser("pause")
    p.add_argument("run_id")

    p = sub.add_parser("resume")
    p.add_argument("run_id")

    p = sub.add_parser("cancel")
    p.add_argument("run_id")

    p = sub.add_parser("approvals")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--approve", default=None)
    p.add_argument("--decision", default="APPROVED")

    p = sub.add_parser("templates")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("replay")
    p.add_argument("run_id")

    p = sub.add_parser("recover")
    p.add_argument("run_id")
    p.add_argument("--worker-id", default=None)

    p = sub.add_parser("tasks")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--status", default=None)

    p = sub.add_parser("sla")
    p.add_argument("run_id")

    p = sub.add_parser("health")

    p = sub.add_parser("anomalies")
    p.add_argument("--limit", type=int, default=20)

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    try:
        if args.action == "list":
            params = {"limit": args.limit}
            if args.status:
                params["status"] = args.status
            res = _call("GET", "/workflows", base, key, params=params)
        elif args.action == "get":
            res = _call("GET", f"/workflows/{args.workflow_id}", base, key)
        elif args.action == "publish":
            body = {}
            if args.version_id:
                body["version_id"] = args.version_id
            res = _call("POST", f"/workflows/{args.workflow_id}/publish", base, key, body=body)
        elif args.action == "run":
            try:
                inputs = json.loads(args.inputs) if isinstance(args.inputs, str) else args.inputs
            except Exception:
                inputs = {}
            body = {"inputs": inputs}
            if args.idempotency_key:
                body["idempotency_key"] = args.idempotency_key
            res = _call("POST", f"/workflows/{args.workflow_id}/trigger", base, key, body=body)
        elif args.action == "status":
            res = _call("GET", f"/workflows/runs/{args.run_id}", base, key)
        elif args.action == "pause":
            res = _call("POST", f"/workflows/runs/{args.run_id}/pause", base, key, body={})
        elif args.action == "resume":
            res = _call("POST", f"/workflows/runs/{args.run_id}/resume", base, key, body={})
        elif args.action == "cancel":
            res = _call("POST", f"/workflows/runs/{args.run_id}/cancel", base, key, body={})
        elif args.action == "approvals":
            if args.approve:
                res = _call("POST", f"/workflows/approvals/{args.approve}/decide", base, key, body={"decision": args.decision})
            else:
                res = _call("GET", "/workflows/approvals", base, key, params={"limit": args.limit})
        elif args.action == "templates":
            res = _call("GET", "/workflows/templates", base, key, params={"limit": args.limit})
        elif args.action == "replay":
            res = _call("POST", f"/workflows/runs/{args.run_id}/replay", base, key, body={})
        elif args.action == "recover":
            body = {}
            if args.worker_id:
                body["worker_id"] = args.worker_id
            res = _call("POST", f"/workflows/runs/{args.run_id}/recover", base, key, body=body)
        elif args.action == "tasks":
            params = {"limit": args.limit}
            if args.status:
                params["status"] = args.status
            res = _call("GET", "/workflows/human-tasks", base, key, params=params)
        elif args.action == "sla":
            res = _call("GET", f"/workflows/sla/{args.run_id}", base, key)
        elif args.action == "health":
            res = _call("GET", "/workflows/health", base, key)
        elif args.action == "anomalies":
            res = _call("GET", "/workflows/anomalies", base, key, params={"limit": args.limit})
        else:
            res = {"error": f"unknown {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
