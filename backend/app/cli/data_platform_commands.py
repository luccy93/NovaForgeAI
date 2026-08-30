"""Data Platform CLI — Volume 65."""

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


def handle_data_platform_command(argv):
    parser = argparse.ArgumentParser(prog="nova data", description="Data Platform CLI (Volume 65)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("datasets")
    p.add_argument("--name", default=None)
    p.add_argument("--classification", default=None)
    p.add_argument("--owner", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--id", default=None)

    p = sub.add_parser("sources")
    p.add_argument("--name", default=None)
    p.add_argument("--connector", default=None)
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("schemas")
    p.add_argument("--dataset-id", default=None)
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("pipelines")
    p.add_argument("--name", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--id", default=None)

    p = sub.add_parser("runs")
    p.add_argument("--pipeline-id", default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("quality")
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("lineage")
    p.add_argument("--node", required=True)
    p.add_argument("--direction", default="upstream", choices=["upstream", "downstream", "graph"])

    p = sub.add_parser("catalog")
    p.add_argument("--q", default=None)
    p.add_argument("--semantic", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("streams")
    p.add_argument("--topic", default=None)
    p.add_argument("--partition", type=int, default=0)
    p.add_argument("--consumer", default=None)
    p.add_argument("--limit", type=int, default=20)

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    try:
        if args.action == "datasets":
            if args.id:
                res = _call("GET", f"/data-platform/datasets/{args.id}", base, key)
            elif args.name:
                res = _call("POST", "/data-platform/datasets", base, key, body={"name": args.name, "classification": args.classification or "INTERNAL"})
            else:
                params = {"limit": args.limit}
                if args.classification:
                    params["classification"] = args.classification
                if args.owner:
                    params["owner"] = args.owner
                res = _call("GET", "/data-platform/datasets", base, key, params=params)
        elif args.action == "sources":
            if args.name:
                res = _call("POST", "/data-platform/sources", base, key, body={"name": args.name, "connector": args.connector or "api"})
            else:
                res = _call("GET", "/data-platform/sources", base, key, params={"limit": args.limit})
        elif args.action == "schemas":
            params = {"limit": args.limit}
            if args.dataset_id:
                params["dataset_id"] = args.dataset_id
            res = _call("GET", "/data-platform/schemas", base, key, params=params)
        elif args.action == "pipelines":
            if args.name:
                res = _call("POST", "/data-platform/pipelines", base, key, body={"name": args.name, "steps": []})
            elif args.id:
                res = _call("GET", f"/data-platform/pipelines/{args.id}", base, key)
            else:
                res = _call("GET", "/data-platform/pipelines", base, key, params={"limit": args.limit})
        elif args.action == "runs":
            if args.run_id:
                res = _call("POST", f"/data-platform/pipelines/runs/{args.run_id}/complete", base, key, body={"status": "SUCCESS"})
            elif args.pipeline_id:
                res = _call("POST", f"/data-platform/pipelines/{args.pipeline_id}/runs", base, key, body={})
            else:
                res = _call("GET", "/data-platform/data-jobs", base, key, params={"limit": args.limit})
        elif args.action == "quality":
            res = _call("GET", "/data-platform/quality/results", base, key, params={"dataset_id": args.dataset_id, "limit": args.limit})
        elif args.action == "lineage":
            if args.direction == "graph":
                res = _call("GET", f"/data-platform/lineage/{args.node}/graph", base, key)
            else:
                res = _call("GET", f"/data-platform/lineage/{args.node}/{args.direction}", base, key)
        elif args.action == "catalog":
            params = {"limit": args.limit, "semantic": args.semantic, "offline": args.offline}
            if args.q:
                params["q"] = args.q
            res = _call("GET", "/data-platform/catalog/search", base, key, params=params)
        elif args.action == "streams":
            if args.topic and args.consumer:
                res = _call("GET", f"/data-platform/streams/{args.topic}/lag", base, key, params={"consumer": args.consumer})
            elif args.topic:
                res = _call("POST", "/data-platform/streams", base, key, body={"topic": args.topic, "partition": args.partition})
            else:
                res = _call("GET", "/data-platform/data-jobs", base, key, params={"limit": args.limit})
        else:
            res = {"error": f"unknown {args.action}"}
        print(json.dumps(res, indent=None if as_json else 2, default=str))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
