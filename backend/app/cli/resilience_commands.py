"""Resilience CLI — Volume 60.

``nova resilience status|backups|backup|verify|restore|plan|recover|failover|readiness|drill|chaos|score|reconcile`` with --json.
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

    # ── Volume 60 Commit 2 ───────────────────────────────────────────────
    sub.add_parser("readiness")
    p = sub.add_parser("score")
    p = sub.add_parser("reconcile"); p.add_argument("job_id"); p.add_argument("--pre", default=None); p.add_argument("--restored", default=None); p.add_argument("--expected", default=None)
    p = sub.add_parser("drill"); p.add_argument("--drill-type", default="backup_restore"); p.add_argument("--scope", default=None); p.add_argument("--schedule", default=None); p.add_argument("--drill-id", default=None); p.add_argument("--run", action="store_true"); p.add_argument("--game-day", action="store_true"); p.add_argument("--scenario", default=None); p.add_argument("--participants", default=None); p.add_argument("--target-environment", default=None)
    p = sub.add_parser("chaos"); p.add_argument("--name", default=None); p.add_argument("--scope", default=None); p.add_argument("--failure-type", default=None); p.add_argument("--test-id", default=None); p.add_argument("--target", default=None); p.add_argument("--run", action="store_true"); p.add_argument("--complete", action="store_true"); p.add_argument("--success", type=lambda x: str(x).lower() not in ("0", "false", "no", "f", "off"), default=True, nargs="?", const=True); p.add_argument("--results", default=None); p.add_argument("--config", default=None); p.add_argument("--inject", action="store_true")

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)
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
        elif args.action == "readiness":
            res = _call("GET", "/resilience/readiness", base, key)
        elif args.action == "score":
            res = _call("GET", "/resilience/resilience-score", base, key)
        elif args.action == "reconcile":
            def _parse(v):
                if v is None:
                    return {}
                if isinstance(v, dict):
                    return v
                try:
                    return json.loads(v)
                except Exception:
                    return {}
            pre = _parse(args.pre)
            restored = _parse(args.restored)
            expected = _parse(args.expected)
            body = {"pre": pre, "pre_state": pre, "restored": restored, "restored_state": restored, "expected": expected, "expected_state": expected}
            res = _call("POST", f"/resilience/reconcile/{args.job_id}", base, key, body=body)
        elif args.action == "drill":
            if args.drill_id and args.run:
                res = _call("POST", f"/resilience/recovery-drills/{args.drill_id}/run", base, key, body={})
            elif args.drill_id and args.game_day:
                body = {}
                if args.scenario:
                    body["scenario"] = args.scenario
                if args.participants:
                    try:
                        body["participants"] = json.loads(args.participants)
                    except Exception:
                        body["participants"] = [args.participants]
                if args.scope:
                    try:
                        body["scope"] = json.loads(args.scope)
                    except Exception:
                        body["scope"] = args.scope
                res = _call("POST", f"/resilience/recovery-drills/{args.drill_id}/game-day", base, key, body=body)
            else:
                body = {"drill_type": args.drill_type}
                if args.scope:
                    try:
                        body["scope"] = json.loads(args.scope)
                    except Exception:
                        body["scope"] = args.scope
                if args.schedule:
                    try:
                        body["schedule"] = json.loads(args.schedule)
                    except Exception:
                        body["schedule"] = args.schedule
                if args.target_environment:
                    body["target_environment"] = args.target_environment
                res = _call("POST", "/resilience/recovery-drills", base, key, body=body)
        elif args.action == "chaos":
            if args.inject:
                test_id = args.test_id or args.target or ""
                target_val = args.target if args.test_id else (args.failure_type or args.target or "")
                body = {"test_id": test_id, "target": target_val}
                if args.failure_type:
                    body["failure_type"] = args.failure_type
                res = _call("POST", "/resilience/chaos/failure-injection", base, key, body=body)
            elif args.test_id and args.run:
                body = {}
                if args.target:
                    body["target"] = args.target
                res = _call("POST", f"/resilience/chaos-tests/{args.test_id}/run", base, key, body=body)
            elif args.test_id and args.complete:
                success = bool(args.success) if not isinstance(args.success, bool) else args.success
                # argparse nargs="?" case: when flag without value, success is True
                if args.success is None:
                    success = True
                body = {"success": success, "passed": success}
                if args.results:
                    try:
                        body["results"] = json.loads(args.results)
                    except Exception:
                        body["results"] = {}
                res = _call("POST", f"/resilience/chaos-tests/{args.test_id}/complete", base, key, body=body)
            else:
                body = {}
                body["name"] = args.name or "chaos-test"
                if args.scope:
                    try:
                        body["scope"] = json.loads(args.scope)
                    except Exception:
                        body["scope"] = args.scope
                else:
                    body["scope"] = "test-scope"
                body["failure_type"] = args.failure_type or "service"
                if args.config:
                    try:
                        body["config"] = json.loads(args.config)
                    except Exception:
                        body["config"] = {}
                if args.target:
                    body["target"] = args.target
                # support data passthrough via scope/config
                res = _call("POST", "/resilience/chaos-tests", base, key, body=body)
        else:
            res = {"error": f"unknown action {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    handle_resilience_command(None)
