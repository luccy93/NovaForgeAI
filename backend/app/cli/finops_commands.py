"""FinOps CLI commands — Volume 69 Commit 1.

Thin HTTP client over /api/v1/finops following the knowledge CLI pattern.
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
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))


def handle_finops_command(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    parser = argparse.ArgumentParser(prog="nova finops")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("usage")
    p_costs = sub.add_parser("costs")
    p_costs.add_argument("--provider", default=None)
    p_costs.add_argument("--model", default=None)
    p_costs.add_argument("--limit", type=int, default=20)
    p_pricing = sub.add_parser("pricing")
    p_pricing.add_argument("--provider", default=None)
    p_budget = sub.add_parser("budget")
    p_budget.add_argument("--name", default=None)
    p_budget.add_argument("--amount-cents", type=int, default=None)
    sub.add_parser("status")
    p_agg = sub.add_parser("aggregate")
    p_agg.add_argument("--granularity", default="day")
    p_agg.add_argument("--start", default=None)
    p_agg.add_argument("--end", default=None)
    p_forecast = sub.add_parser("forecast")
    p_forecast.add_argument("--horizon-days", type=int, default=30)
    sub.add_parser("anomalies")
    sub.add_parser("recommend")
    p_compare = sub.add_parser("compare")
    p_compare.add_argument("--provider", default=None)
    sub.add_parser("policies")
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("--operation", required=True)
    p_gate.add_argument("--estimated-cents", type=int, default=0)
    p_report = sub.add_parser("report")
    p_report.add_argument("--type", default="showback")
    p_report.add_argument("--group-by", default="workspace")

    args = parser.parse_args(argv)
    base, key = _base(args.base_url), _key(args.api_key)
    if args.cmd == "usage":
        _out(_call("GET", "/finops/usage/summary", base, key), as_json)
    elif args.cmd == "costs":
        params = {"limit": args.limit}
        if args.provider:
            params["provider"] = args.provider
        if args.model:
            params["model"] = args.model
        _out(_call("GET", "/finops/costs", base, key, params=params), as_json)
    elif args.cmd == "pricing":
        params = {}
        if args.provider:
            params["provider"] = args.provider
        _out(_call("GET", "/finops/pricing", base, key, params=params), as_json)
    elif args.cmd == "budget":
        if args.name and args.amount_cents:
            _out(_call("POST", "/finops/budgets", base, key,
                       body={"name": args.name, "amount_cents": args.amount_cents}), as_json)
        else:
            _out(_call("GET", "/finops/budgets", base, key), as_json)
    elif args.cmd == "status":
        _out(_call("GET", "/finops/budgets", base, key), as_json)
    elif args.cmd == "aggregate":
        _out(_call("POST", "/finops/aggregations/run", base, key, body={
            "granularity": args.granularity, "start": args.start, "end": args.end, "dimensions": {},
        }), as_json)
    elif args.cmd == "forecast":
        _out(_call("GET", "/finops/forecast", base, key,
                   params={"horizon_days": args.horizon_days}), as_json)
    elif args.cmd == "anomalies":
        _out(_call("GET", "/finops/anomalies", base, key), as_json)
    elif args.cmd == "recommend":
        _out(_call("POST", "/finops/recommendations/generate", base, key, body={}), as_json)
    elif args.cmd == "compare":
        params = {}
        if args.provider:
            params["provider"] = args.provider
        _out(_call("GET", "/finops/models/compare", base, key, params=params), as_json)
    elif args.cmd == "policies":
        _out(_call("GET", "/finops/policies", base, key), as_json)
    elif args.cmd == "gate":
        _out(_call("POST", "/finops/gate/evaluate", base, key, body={
            "operation": args.operation, "estimated_cents": args.estimated_cents}), as_json)
    elif args.cmd == "report":
        _out(_call("POST", f"/finops/reports/{args.type}", base, key,
                   body={"group_by": args.group_by}), as_json)
    else:
        parser.print_help()
