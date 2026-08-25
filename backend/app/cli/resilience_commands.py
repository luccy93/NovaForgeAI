"""Resilience CLI — Volume 60.

``nova resilience status|backups|backup|verify|restore|plan|recover|failover`` with --json.
"""

import argparse, json, os, sys
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


def handle_resilience_command(argv):
    parser = argparse.ArgumentParser(prog="nova resilience", description="Resilience CLI (Volume 60)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("status")
    p = sub.add_parser("backups"); p.add_argument("--scope-type", default=None)
    p = sub.add_parser("backup"); p.add_argument("--scope-type", required=True); p.add_argument("--scope-target", default=None); p.add_argument("--backup-type", default="full"); p.add_argument("--complete", action="store_true")
    p = sub.add_parser("verify"); p.add_argument("backup_id"); p.add_argument("--verification-type", default="checksum"); p.add_argument("--expected-checksum", default=None)
    p = sub.add_parser("restore"); p.add_argument("backup_id"); p.add_argument("--mode", default="full"); p.add_argument("--isolated-test", action="store_true"); p.add_argument("--run", action="store_true")
    p = sub.add_parser("plan"); p.add_argument("--name", required=True); p.add_argument("--service", required=True)
    p = sub.add_parser("recover"); p.add_argument("plan_id")
    p = sub.add_parser("failover"); p.add_argument("--failover-type", required=True); p.add_argument("--source", default=None); p.add_argument("--destination", default=None)

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False))
    try:
        if args.action == "status":
            res = _call("GET", "/resilience/dashboard", base, key)
        elif args.action == "backups":
            params = {"scope_type": args.scope_type} if args.scope_type else {}
            res = _call("GET", "/resilience/backups", base, key, params=params)
        elif args.action == "backup":
            body = {"scope_type": args.scope_type, "scope_target": args.scope_target,
                    "backup_type": args.backup_type, "complete_immediately": args.complete}
            res = _call("POST", "/resilience/backups", base, key, body=body)
        elif args.action == "verify":
            res = _call("POST", f"/resilience/backups/{args.backup_id}/verify", base, key,
                        body={"verification_type": args.verification_type, "expected_checksum": args.expected_checksum})
        elif args.action == "restore":
            res = _call("POST", "/resilience/restore", base, key,
                        body={"backup_id": args.backup_id, "mode": args.mode, "isolated_test": args.isolated_test})
            if args.run and isinstance(res, dict) and res.get("id"):
                job_id = res["id"]
                state = res.get("state")
                if state in ("READY", "PLANNED"):
                    res = _call("POST", f"/resilience/restore/{job_id}/run", base, key, body={})
        elif args.action == "plan":
            res = _call("POST", "/resilience/recovery-plans", base, key,
                        body={"name": args.name, "service": args.service, "steps": []})
        elif args.action == "recover":
            res = _call("POST", f"/resilience/recovery-plans/{args.plan_id}/execute", base, key, body={})
        elif args.action == "failover":
            res = _call("POST", "/resilience/failovers", base, key,
                        body={"failover_type": args.failover_type, "source_target": args.source,
                              "destination_target": args.destination})
        else:
            res = {"error": f"unknown action {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    handle_resilience_command()
