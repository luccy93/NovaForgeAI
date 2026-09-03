"""Knowledge CLI — Volume 68."""

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
    with httpx.Client(timeout=60) as client:
        resp = client.request(method, url, headers=headers, json=body, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}


def _out(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    print(f"{k}:")
                    print(json.dumps(v, indent=2, default=str))
                else:
                    print(f"{k}: {v}")
        else:
            print(data)


def handle_knowledge_command(argv):
    parser = argparse.ArgumentParser(prog="nova knowledge", description="Knowledge & Search CLI (Volume 68)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--source-type", default=None)
    p.add_argument("--doc-type", default=None)
    p.add_argument("--classification", default=None)
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("sources")
    p.add_argument("--status", default=None)
    p.add_argument("--create", action="store_true")
    p.add_argument("--name", default=None)
    p.add_argument("--type", dest="source_type", default=None)
    p.add_argument("--delete", default=None)

    p = sub.add_parser("documents")
    p.add_argument("document_id", nargs="?", default=None)
    p.add_argument("--source-id", default=None)
    p.add_argument("--external-id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--content", default=None)

    p = sub.add_parser("ingest")
    p.add_argument("--source-id", required=True)
    p.add_argument("--type", dest="job_type", default="incremental")

    p = sub.add_parser("jobs")
    p.add_argument("--source-id", default=None)
    p.add_argument("--get", default=None)

    p = sub.add_parser("entities")
    p.add_argument("--type", dest="entity_type", default=None)
    p.add_argument("--create", action="store_true")
    p.add_argument("--name", default=None)
    p.add_argument("--entity-type", default=None)

    p = sub.add_parser("links")
    p.add_argument("--source-entity", default=None)
    p.add_argument("--target-entity", default=None)
    p.add_argument("--link-type", default=None)

    p = sub.add_parser("freshness")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--mark-stale", action="store_true")
    p.add_argument("--hours", type=int, default=168)

    p = sub.add_parser("usage")
    p.add_argument("--since-hours", type=int, default=24)

    p = sub.add_parser("reindex")
    p.add_argument("--source-id", required=True)

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    action = args.action

    if action == "search":
        params = {"query": args.query, "limit": args.limit}
        if args.source_type:
            params["source_type"] = args.source_type
        if args.doc_type:
            params["doc_type"] = args.doc_type
        if args.classification:
            params["classification"] = args.classification
        _out(_call("GET", "/knowledge/search", base, key, params=params), as_json)

    elif action == "sources":
        if args.create:
            body = {"name": args.name or "unnamed", "source_type": args.source_type or "external"}
            _out(_call("POST", "/knowledge/sources", base, key, body=body), as_json)
            return
        if args.delete:
            _out(_call("DELETE", f"/knowledge/sources/{args.delete}", base, key), as_json)
            return
        params = {}
        if args.status:
            params["status"] = args.status
        _out(_call("GET", "/knowledge/sources", base, key, params=params), as_json)

    elif action == "documents":
        if args.document_id:
            _out(_call("GET", f"/knowledge/documents/{args.document_id}", base, key), as_json)
        elif args.source_id and args.external_id:
            body = {
                "source_id": args.source_id,
                "external_id": args.external_id,
                "title": args.title or "",
                "content": args.content or "",
            }
            _out(_call("POST", "/knowledge/documents", base, key, body=body), as_json)
        else:
            print("Usage: knowledge documents <document_id> OR --source-id + --external-id + --title + --content")

    elif action == "ingest":
        body = {"source_id": args.source_id, "job_type": args.job_type}
        _out(_call("POST", "/knowledge/ingestion/jobs", base, key, body=body), as_json)

    elif action == "jobs":
        if args.get:
            _out(_call("GET", f"/knowledge/ingestion/jobs/{args.get}", base, key), as_json)
        else:
            params = {}
            if args.source_id:
                params["source_id"] = args.source_id
            _out(_call("GET", "/knowledge/ingestion/jobs", base, key, params=params), as_json)

    elif action == "entities":
        if args.create:
            body = {"entity_type": args.entity_type or "concept", "name": args.name or "unnamed"}
            _out(_call("POST", "/knowledge/entities", base, key, body=body), as_json)
        else:
            params = {}
            if args.type:
                params["entity_type"] = args.type
            _out(_call("GET", "/knowledge/entities", base, key, params=params), as_json)

    elif action == "links":
        if args.source_entity and args.target_entity and args.link_type:
            body = {
                "source_entity_id": args.source_entity,
                "target_entity_id": args.target_entity,
                "link_type": args.link_type,
            }
            _out(_call("POST", "/knowledge/links", base, key, body=body), as_json)
        else:
            print("Usage: knowledge links --source-entity <id> --target-entity <id> --link-type <type>")

    elif action == "freshness":
        if args.mark_stale:
            _out(_call("POST", "/knowledge/freshness/mark-stale", base, key, body={"older_than_hours": args.hours}), as_json)
        else:
            _out(_call("GET", "/knowledge/freshness/stats", base, key), as_json)

    elif action == "usage":
        _out(_call("GET", "/knowledge/audit/usage", base, key, params={"since_hours": args.since_hours}), as_json)

    elif action == "reindex":
        _out(_call("POST", "/knowledge/ingestion/reindex", base, key, body={"source_id": args.source_id}), as_json)

    else:
        parser.error("unknown action")
