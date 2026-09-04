"""Integrations CLI commands — Volume 70 Commit 1.

Thin HTTP client over /api/v1/integrations following the domain CLI
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


def handle_integrations_command(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    parser = argparse.ArgumentParser(prog="nova integrations")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list")
    p_create = sub.add_parser("create")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--type", required=True)
    p_create.add_argument("--provider", default="")
    p_status = sub.add_parser("status")
    p_status.add_argument("--id", required=True)
    p_conn = sub.add_parser("connections")
    p_conn.add_argument("--integration-id", default=None)
    p_wh = sub.add_parser("webhooks")
    p_wh.add_argument("--name", default=None)
    p_wh.add_argument("--url", default=None)
    p_health = sub.add_parser("health")
    p_health.add_argument("--connection-id", required=True)
    p_oauth = sub.add_parser("oauth")
    p_oauth.add_argument("--integration-id", default=None)
    p_oauth.add_argument("--action", default="list", choices=["list", "revoke"])
    p_oauth.add_argument("--id", default=None)
    sub.add_parser("connectors")
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--connection-id", required=True)
    p_revoke = sub.add_parser("revoke")
    p_revoke.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    base, key = _base(args.base_url), _key(args.api_key)
    if args.cmd == "list":
        _out(_call("GET", "/integrations", base, key), as_json)
    elif args.cmd == "create":
        _out(_call("POST", "/integrations", base, key, body={
            "name": args.name, "type": args.type, "provider": args.provider}), as_json)
    elif args.cmd == "status":
        _out(_call("GET", f"/integrations/{args.id}", base, key), as_json)
    elif args.cmd == "connections":
        params = {}
        if args.integration_id:
            params["integration_id"] = args.integration_id
        _out(_call("GET", "/integrations/connections/all", base, key, params=params), as_json)
    elif args.cmd == "webhooks":
        if args.name and args.url:
            _out(_call("POST", "/integrations/webhooks", base, key,
                       body={"name": args.name, "url": args.url}), as_json)
        else:
            _out(_call("GET", "/integrations/webhooks/all", base, key), as_json)
    elif args.cmd == "health":
        _out(_call("POST", f"/integrations/connections/{args.connection_id}/health",
                   base, key, body={}), as_json)
    elif args.cmd == "oauth":
        if args.action == "revoke" and args.id:
            _out(_call("POST", f"/integrations/oauth/{args.id}/revoke", base, key, body={}), as_json)
        else:
            _out(_call("GET", "/integrations/oauth", base, key), as_json)
    elif args.cmd == "connectors":
        _out(_call("GET", "/integrations/connectors/available", base, key), as_json)
    elif args.cmd == "sync":
        _out(_call("POST", f"/integrations/connections/{args.connection_id}/sync",
                   base, key, body={}), as_json)
    elif args.cmd == "revoke":
        _out(_call("POST", f"/integrations/{args.id}/status", base, key,
                   body={"status": "REVOKED"}), as_json)
    else:
        parser.print_help()
