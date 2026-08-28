"""Multi-Region CLI — Volume 62 Commit 1.

``nova region list|status|placement|health|failover|failback|replication`` with --json.
"""

import argparse
import json
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


def handle_region_command(argv):
    parser = argparse.ArgumentParser(prog="nova region", description="Multi-Region CLI (Volume 62)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("list")
    p.add_argument("--status", default=None)
    p = sub.add_parser("status"); p.add_argument("region_id"); p.add_argument("--status", default=None); p.add_argument("--reason", default=None)
    p = sub.add_parser("register"); p.add_argument("--region-id", required=True); p.add_argument("--name", required=True); p.add_argument("--provider", required=True); p.add_argument("--location", required=True); p.add_argument("--environment", default="production"); p.add_argument("--capabilities", default=None); p.add_argument("--status", default="ACTIVE")
    p = sub.add_parser("capabilities"); p.add_argument("region_id"); p.add_argument("--set", default=None)
    p = sub.add_parser("health"); p.add_argument("region_id"); p.add_argument("--status", default=None); p.add_argument("--all", action="store_true")
    p = sub.add_parser("capacity"); p.add_argument("region_id")
    p = sub.add_parser("drain"); p.add_argument("region_id"); p.add_argument("--reason", default=None)
    p = sub.add_parser("drain-complete"); p.add_argument("region_id")

    p = sub.add_parser("placement"); p.add_argument("--tenant", default=None); p.add_argument("--primary", default=None); p.add_argument("--secondary", default=None); p.add_argument("--allowed", default=None); p.add_argument("--set", action="store_true")
    p = sub.add_parser("evaluate"); p.add_argument("--tenant", required=True); p.add_argument("--region", required=True); p.add_argument("--classification", default=None); p.add_argument("--provider", default=None)

    p = sub.add_parser("route"); p.add_argument("--service", required=True); p.add_argument("--classification", default=None); p.add_argument("--preferred", default=None); p.add_argument("--criticality", default="HIGH")
    p = sub.add_parser("policy"); p.add_argument("--service", required=True); p.add_argument("--primary", default=None); p.add_argument("--secondary", default=None); p.add_argument("--fallback", default=None); p.add_argument("--consistency", default="CONFIGURABLE")
    p = sub.add_parser("config"); p.add_argument("--service", required=True); p.add_argument("--primary", default=None); p.add_argument("--secondary", default=None); p.add_argument("--fallback", default=None); p.add_argument("--consistency", default="CONFIGURABLE"); p.add_argument("--list", action="store_true")

    p = sub.add_parser("replication"); p.add_argument("--source", required=True); p.add_argument("--dest", required=True); p.add_argument("--resource", required=True); p.add_argument("--status", default="HEALTHY"); p.add_argument("--lag", type=float, default=0.0); p.add_argument("--list", action="store_true")

    p = sub.add_parser("failover"); p.add_argument("--source", required=True); p.add_argument("--target", required=True); p.add_argument("--service", default=None); p.add_argument("--classification", default=None); p.add_argument("--complete", type=int, default=None); p.add_argument("--fail", type=int, default=None)
    p = sub.add_parser("failback"); p.add_argument("--source", required=True); p.add_argument("--target", required=True); p.add_argument("--service", default=None); p.add_argument("--classification", default=None)

    # Commit 2 CLI
    p = sub.add_parser("orchestrate"); p.add_argument("--source", required=True); p.add_argument("--target", required=True); p.add_argument("--service", required=True); p.add_argument("--classification", default=None); p.add_argument("--authorized-by", default=None); p.add_argument("--automatic", action="store_true"); p.add_argument("--rpo", type=int, default=None)
    p = sub.add_parser("recovery-verify"); p.add_argument("--source", required=True); p.add_argument("--target", required=True)
    p = sub.add_parser("lease"); p.add_argument("--region-id", required=True); p.add_argument("--holder", required=True); p.add_argument("--ttl", type=int, default=60); p.add_argument("--generation", type=int, default=1)
    p = sub.add_parser("fence"); p.add_argument("--region-id", required=True)
    p = sub.add_parser("stale"); p.add_argument("--region-id", required=True)
    p = sub.add_parser("conflict"); p.add_argument("--source", required=True); p.add_argument("--dest", required=True); p.add_argument("--resource", required=True); p.add_argument("--type", default="version"); p.add_argument("--resolve", type=int, default=None); p.add_argument("--policy", default=None); p.add_argument("--tenant", default="")
    p = sub.add_parser("migration"); p.add_argument("--source", required=True); p.add_argument("--target", required=True); p.add_argument("--authorized-by", required=True); p.add_argument("--service", default=None); p.add_argument("--classification", default=None); p.add_argument("--rollback-strategy", default=None); p.add_argument("--advance", type=int, default=None); p.add_argument("--state", default=None); p.add_argument("--verify", type=int, default=None); p.add_argument("--rollback", type=int, default=None)
    p = sub.add_parser("traffic"); p.add_argument("--region-id", required=True); p.add_argument("--percentage", type=int, required=True); p.add_argument("--get", action="store_true")
    p = sub.add_parser("rejoin"); p.add_argument("--region-id", required=True); p.add_argument("--compromised", action="store_true"); p.add_argument("--verify", action="store_true"); p.add_argument("--source", default=None); p.add_argument("--admit", action="store_true")
    p = sub.add_parser("drift"); p.add_argument("--service", required=True); p.add_argument("--expected", required=True); p.add_argument("--observed", required=True); p.add_argument("--resolve", type=int, default=None)
    p = sub.add_parser("drill"); p.add_argument("--scenario", required=True); p.add_argument("--region-id", default=None)
    p = sub.add_parser("aiops"); p.add_argument("--region-id", required=True); p.add_argument("--signals", default="{}")

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    try:
        if args.action == "list":
            params = {"status": args.status} if args.status else {}
            res = _call("GET", "/regions/regions", base, key, params=params or None)
        elif args.action == "status":
            body = {"status": args.status}
            if args.reason:
                body["reason"] = args.reason
            res = _call("PATCH", f"/regions/regions/{args.region_id}/status", base, key, body=body)
        elif args.action == "register":
            caps = {}
            if args.capabilities:
                try:
                    caps = json.loads(args.capabilities)
                except Exception:
                    caps = {}
            res = _call("POST", "/regions/regions", base, key, body={"region_id": args.region_id, "name": args.name,
                         "provider": args.provider, "location": args.location, "environment": args.environment,
                         "capabilities": caps, "status": args.status})
        elif args.action == "capabilities":
            if args.set:
                try:
                    caps = json.loads(args.set)
                except Exception:
                    caps = {}
                res = _call("POST", f"/regions/regions/{args.region_id}/capabilities", base, key, body={"capabilities": caps})
            else:
                res = _call("GET", f"/regions/regions/{args.region_id}/capabilities", base, key)
        elif args.action == "health":
            if args.all:
                res = _call("GET", "/regions/regions/health", base, key)
            elif args.status:
                res = _call("POST", f"/regions/regions/{args.region_id}/health", base, key, body={"status": args.status, "checks": {}})
            else:
                res = _call("GET", f"/regions/regions/{args.region_id}/health", base, key)
        elif args.action == "capacity":
            res = _call("GET", f"/regions/regions/{args.region_id}/capacity", base, key)
        elif args.action == "drain":
            res = _call("POST", f"/regions/regions/{args.region_id}/drain", base, key, body={"reason": args.reason} if args.reason else {})
        elif args.action == "drain-complete":
            res = _call("POST", f"/regions/regions/{args.region_id}/drain/complete", base, key, body={})
        elif args.action == "placement":
            if args.set:
                allowed = []
                if args.allowed:
                    try:
                        allowed = json.loads(args.allowed)
                    except Exception:
                        allowed = [x.strip() for x in args.allowed.split(",") if x.strip()]
                res = _call("POST", "/regions/placements", base, key, body={"primary_region": args.primary,
                         "secondary_region": args.secondary, "allowed_regions": allowed})
            else:
                tid = args.tenant or ""
                res = _call("GET", f"/regions/placements/{tid}", base, key) if tid else {"error": "provide --tenant or --set"}
        elif args.action == "evaluate":
            res = _call("POST", f"/regions/placements/{args.tenant}/evaluate", base, key,
                        body={"region": args.region, "data_classification": args.classification, "provider": args.provider})
        elif args.action == "route":
            res = _call("POST", "/regions/routing/resolve", base, key, body={"service": args.service,
                         "data_classification": args.classification, "preferred_region": args.preferred, "criticality": args.criticality})
        elif args.action == "policy":
            res = _call("POST", "/regions/routing-policies", base, key, body={"service": args.service,
                         "primary_region": args.primary, "preferred_secondary": args.secondary,
                         "emergency_fallback": args.fallback, "consistency": args.consistency})
        elif args.action == "config":
            if args.list:
                res = _call("GET", "/regions/config", base, key)
            else:
                res = _call("POST", "/regions/config", base, key, body={"service": args.service,
                         "primary_region": args.primary, "preferred_secondary": args.secondary,
                         "emergency_fallback": args.fallback, "consistency": args.consistency})
        elif args.action == "replication":
            if args.list:
                res = _call("GET", "/regions/replication", base, key)
            else:
                res = _call("POST", "/regions/replication", base, key, body={"source_region": args.source,
                         "dest_region": args.dest, "resource": args.resource, "status": args.status, "lag_seconds": args.lag})
        elif args.action == "failover":
            if args.complete is not None:
                res = _call("POST", f"/regions/failover/{args.complete}/complete", base, key, body={})
            elif args.fail is not None:
                res = _call("POST", f"/regions/failover/{args.fail}/fail", base, key, body={})
            else:
                res = _call("POST", "/regions/failover", base, key, body={"source_region": args.source,
                         "target_region": args.target, "service": args.service, "data_classification": args.classification})
        elif args.action == "failback":
            res = _call("POST", "/regions/failover", base, key, body={"source_region": args.source,
                      "target_region": args.target, "service": args.service, "data_classification": args.classification,
                      "failover_type": "failback"})
        # Commit 2 handlers
        elif args.action == "orchestrate":
            res = _call("POST", "/regions/orchestrate", base, key, body={"source_region": args.source,
                      "target_region": args.target, "service": args.service, "data_classification": args.classification,
                      "authorized_by": args.authorized_by, "automatic": args.automatic, "rpo_minutes": args.rpo})
        elif args.action == "recovery-verify":
            res = _call("POST", "/regions/recovery/verify", base, key, body={"source_region": args.source, "target_region": args.target, "checks": {}})
        elif args.action == "lease":
            res = _call("POST", "/regions/lease", base, key, body={"region_id": args.region_id, "holder": args.holder, "ttl_seconds": args.ttl, "generation": args.generation})
        elif args.action == "fence":
            res = _call("POST", f"/regions/lease/{args.region_id}/fence", base, key, body={})
        elif args.action == "stale":
            res = _call("GET", f"/regions/lease/{args.region_id}/stale", base, key)
        elif args.action == "conflict":
            if args.resolve is not None:
                res = _call("POST", f"/regions/conflicts/{args.resolve}/resolve", base, key, body={"policy": args.policy or "MANUAL_REVIEW"})
            else:
                res = _call("POST", "/regions/conflicts", base, key, body={"source_region": args.source, "dest_region": args.dest,
                          "resource": args.resource, "conflict_type": args.type, "tenant": args.tenant})
        elif args.action == "migration":
            if args.advance is not None:
                res = _call("POST", f"/regions/migrations/{args.advance}/advance", base, key, body={"state": args.state})
            elif args.verify is not None:
                res = _call("POST", f"/regions/migrations/{args.verify}/verify", base, key, body={"verification": {}})
            elif args.rollback is not None:
                res = _call("POST", f"/regions/migrations/{args.rollback}/rollback", base, key, body={})
            else:
                res = _call("POST", "/regions/migrations", base, key, body={"source_region": args.source, "target_region": args.target,
                          "authorized_by": args.authorized_by, "service": args.service, "data_classification": args.classification,
                          "rollback_strategy": args.rollback_strategy})
        elif args.action == "traffic":
            if args.get:
                res = _call("GET", f"/regions/traffic/{args.region_id}", base, key)
            else:
                res = _call("POST", "/regions/traffic", base, key, body={"region_id": args.region_id, "percentage": args.percentage})
        elif args.action == "rejoin":
            if args.admit:
                res = _call("POST", f"/regions/rejoin/{args.region_id}/admit", base, key, body={})
            elif args.verify:
                res = _call("POST", "/regions/rejoin/verify", base, key, body={"region_id": args.region_id, "source_region": args.source or "", "checks": {}})
            else:
                res = _call("POST", "/regions/rejoin", base, key, body={"region_id": args.region_id, "compromised": args.compromised})
        elif args.action == "drift":
            if args.resolve is not None:
                res = _call("POST", f"/regions/drifts/{args.resolve}/resolve", base, key, body={})
            else:
                res = _call("POST", "/regions/drift", base, key, body={"service": args.service, "expected_version": args.expected, "observed_version": args.observed})
        elif args.action == "drill":
            res = _call("POST", "/regions/drills", base, key, body={"scenario": args.scenario, "region_id": args.region_id})
        elif args.action == "aiops":
            try:
                signals = json.loads(args.signals)
            except Exception:
                signals = {}
            res = _call("POST", "/regions/aiops/recommend", base, key, body={"region_id": args.region_id, "signals": signals})
        else:
            res = {"error": f"unknown action {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


import os  # noqa: E402
