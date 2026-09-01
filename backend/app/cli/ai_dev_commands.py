"""AI Developer Experience CLI — Volume 67."""

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


def handle_ai_dev_command(argv):
    parser = argparse.ArgumentParser(prog="nova ai-dev", description="AI Developer Experience CLI (Volume 67)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("workspaces")
    p.add_argument("--repository-id", default=None)
    p.add_argument("--create", default=None)
    p.add_argument("--name", default="workspace")

    p = sub.add_parser("search")
    p.add_argument("repository_id")
    p.add_argument("query")
    p.add_argument("--symbol-type", default=None)
    p.add_argument("--limit", type=int, default=12)

    p = sub.add_parser("chat")
    p.add_argument("repository_id")
    p.add_argument("question")
    p.add_argument("--model-hint", default=None)

    p = sub.add_parser("explain")
    p.add_argument("repository_id")
    p.add_argument("kind")
    p.add_argument("target")

    p = sub.add_parser("patch")
    p.add_argument("repository_id")
    p.add_argument("title")
    p.add_argument("--files", default="[]")
    p.add_argument("--apply", default=None)
    p.add_argument("--current", default="{}")
    p.add_argument("--rollback", default=None)

    p = sub.add_parser("review")
    p.add_argument("repository_id")
    p.add_argument("--files", default="[]")
    p.add_argument("--get", default=None)

    p = sub.add_parser("test")
    p.add_argument("repository_id")
    p.add_argument("--generate", action="store_true")
    p.add_argument("--execute", default=None)
    p.add_argument("--result", default=None)
    p.add_argument("--status", default="PASSED")

    p = sub.add_parser("fix")
    p.add_argument("repository_id")
    p.add_argument("goal")
    p.add_argument("patch_title")
    p.add_argument("--files", default="[]")
    p.add_argument("--patches", default="[]")

    p = sub.add_parser("blast-radius")
    p.add_argument("repository_id")
    p.add_argument("target")

    p = sub.add_parser("usage")
    p.add_argument("--action", default=None)

    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json_raw = "--json" in raw_argv
    filtered_argv = [a for a in raw_argv if a != "--json"]
    args = parser.parse_args(filtered_argv)
    base = _base(args.base_url)
    key = _key(args.api_key)
    as_json = bool(getattr(args, "as_json", False) or as_json_raw)

    action = args.action

    if action == "workspaces":
        if args.create:
            data = _call("POST", "/ai-dev/workspaces", base, key, body={
                "name": args.name or "workspace",
                "repository_id": args.create,
                "branch": "main",
            })
            _out(data, as_json)
            return
        params = {"limit": 50} if not args.repository_id else {"repository_id": args.repository_id, "limit": 50}
        _out(_call("GET", "/ai-dev/workspaces", base, key, params=params), as_json)
    elif action == "search":
        params = {"q": args.query, "limit": args.limit}
        if args.symbol_type:
            params["symbol_type"] = args.symbol_type
        _out(_call("GET", f"/ai-dev/repositories/{args.repository_id}/search", base, key, params=params), as_json)
    elif action == "chat":
        body = {"repository_id": args.repository_id, "question": args.question}
        if args.model_hint:
            body["model_hint"] = args.model_hint
        _out(_call("POST", "/ai-dev/chat", base, key, body=body), as_json)
    elif action == "explain":
        _out(_call("POST", "/ai-dev/explain", base, key, body={
            "repository_id": args.repository_id,
            "kind": args.kind,
            "target": args.target,
        }), as_json)
    elif action == "patch":
        if args.apply:
            _out(_call("POST", f"/ai-dev/patches/{args.apply}/apply", base, key, body={
                "current_files": json.loads(args.current),
            }), as_json)
        elif args.rollback:
            _out(_call("POST", f"/ai-dev/patches/{args.rollback}/rollback", base, key, body={}), as_json)
        else:
            files = json.loads(args.files)
            _out(_call("POST", "/ai-dev/patch", base, key, body={
                "repository_id": args.repository_id,
                "title": args.title,
                "files": files,
                "source": "cli",
            }), as_json)
    elif action == "review":
        if args.get:
            _out(_call("GET", f"/ai-dev/reviews/{args.get}", base, key), as_json)
        else:
            files = json.loads(args.files)
            _out(_call("POST", "/ai-dev/review", base, key, body={
                "repository_id": args.repository_id,
                "files": files,
            }), as_json)
    elif action == "test":
        if args.execute:
            _out(_call("POST", f"/ai-dev/tests/{args.execute}/execute", base, key, body={}), as_json)
        elif args.result:
            _out(_call("POST", f"/ai-dev/tests/{args.result}/result", base, key, body={
                "status": args.status,
            }), as_json)
        else:
            _out(_call("POST", "/ai-dev/tests/generate", base, key, body={
                "repository_id": args.repository_id,
            }), as_json)
    elif action == "fix":
        files = json.loads(args.files)
        patches = json.loads(args.patches)
        if patches:
            for pid in patches:
                _out(_call("GET", f"/ai-dev/patches/{pid}", base, key), as_json)
        else:
            _out(_call("POST", "/ai-dev/fix", base, key, body={
                "repository_id": args.repository_id,
                "files": files,
                "goal": args.goal,
                "patch_title": args.patch_title,
                "max_iterations": 3,
            }), as_json)
    elif action == "blast-radius":
        data = _call("POST", "/ai-dev/explain", base, key, body={
            "repository_id": args.repository_id,
            "kind": "function",
            "target": args.target,
        })
        _out(data, as_json)
    elif action == "usage":
        params = {"limit": 50} if not args.action else {"action": args.action, "limit": 50}
        _out(_call("GET", "/ai-dev/usage", base, key, params=params), as_json)
    else:  # pragma: no cover - argparse enforces
        parser.error("unknown action")