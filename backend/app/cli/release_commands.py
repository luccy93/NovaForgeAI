"""Release CLI — Volume 56.

Handles ``nova release create/validate/approve/deploy/status/promote/pause/rollback/verify``
and ``nova flag create/get/set/rollout/archive/evaluate`` via ``handle_release_command(args)``.

Uses argparse, supports --json and --ci, calls API via httpx.
Additive, real implementation with proper env/base-url resolution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# Helpers — base url / auth / output
# ---------------------------------------------------------------------------

def _resolve_base_url(explicit: Optional[str] = None) -> str:
    return (
        explicit
        or os.environ.get("NOVAFORGE_BASE_URL")
        or os.environ.get("BACKEND_URL")
        or os.environ.get("API_BASE_URL")
        or "http://localhost:8000"
    ).rstrip("/")


def _resolve_api_key(explicit: Optional[str] = None) -> Optional[str]:
    return explicit or os.environ.get("NOVAFORGE_API_KEY") or os.environ.get("API_KEY")


def _headers(api_key: Optional[str] = None) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
        h["X-API-Key"] = api_key
    return h


def _print_result(data: Any, as_json: bool, ci: bool) -> None:
    """Print data; --json forces JSON, --ci uses compact JSON on stdout only."""
    if as_json or ci:
        print(json.dumps(data, indent=None if ci else 2, default=str))
        return
    # human readable fallback — still JSON but pretty
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(str(data))


def _print_error(msg: str, ci: bool = False) -> None:
    # in CI mode errors go to stderr as JSON for machine parsing
    if ci:
        print(json.dumps({"error": msg}, default=str), file=sys.stderr)
    else:
        print(f"Error: {msg}", file=sys.stderr)


def _api_call(method: str, path: str, base_url: str, api_key: Optional[str], json_body: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    url = f"{base_url}/api/v1{path}" if not path.startswith("/api") else f"{base_url}{path}"
    headers = _headers(api_key)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, headers=headers, json=json_body, params=params)
            resp.raise_for_status()
            if resp.content:
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text, "status_code": resp.status_code}
            return {"status_code": resp.status_code}
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        try:
            detail = exc.response.json()
        except Exception:
            detail = body
        raise RuntimeError(f"HTTP {exc.response.status_code}: {detail}") from exc
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Cannot connect to {base_url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Release subcommands
# ---------------------------------------------------------------------------

def _cmd_release_create(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    # args provides project, service, version, artifact_id, environment, release_channel, strategy, commit_sha, build_id, metadata
    payload: dict[str, Any] = {
        "project": args.project,
        "service": args.service,
        "version": args.version,
        "artifact_id": args.artifact_id,
        "environment": getattr(args, "environment", "DEV") or "DEV",
        "release_channel": getattr(args, "release_channel", "DEV") or "DEV",
        "strategy": getattr(args, "strategy", "rolling") or "rolling",
    }
    if getattr(args, "commit_sha", None):
        payload["commit_sha"] = args.commit_sha
    if getattr(args, "build_id", None):
        payload["build_id"] = args.build_id
    # metadata as JSON string or dict
    meta = getattr(args, "metadata", None)
    if meta:
        try:
            payload["metadata"] = json.loads(meta) if isinstance(meta, str) else dict(meta)
        except Exception:
            payload["metadata"] = {"raw": meta}
    else:
        payload["metadata"] = {}
    return _api_call("POST", "/releases", base_url, api_key, json_body=payload)


def _cmd_release_validate(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("POST", f"/releases/{args.release_id}/validate", base_url, api_key)


def _cmd_release_approve(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    payload: dict[str, Any] = {
        "approver_role": getattr(args, "approver_role", "reviewer") or "reviewer",
        "decision": getattr(args, "decision", "approved") or "approved",
    }
    if getattr(args, "reason", None):
        payload["reason"] = args.reason
    if getattr(args, "signature", None):
        payload["signature"] = args.signature
    if getattr(args, "version", None):
        payload["version"] = args.version
    return _api_call("POST", f"/releases/{args.release_id}/approvals", base_url, api_key, json_body=payload)


def _cmd_release_deploy(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("POST", f"/releases/{args.release_id}/deploy", base_url, api_key)


def _cmd_release_status(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("GET", f"/releases/{args.release_id}/status", base_url, api_key)


def _cmd_release_promote(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("POST", f"/releases/{args.release_id}/promote", base_url, api_key, json_body={"target_env": args.target_env})


def _cmd_release_pause(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    payload: dict[str, Any] = {}
    if getattr(args, "reason", None):
        payload["reason"] = args.reason
    return _api_call("POST", f"/releases/{args.release_id}/pause", base_url, api_key, json_body=payload)


def _cmd_release_rollback(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    payload: dict[str, Any] = {"reason": getattr(args, "reason", "manual rollback") or "manual rollback"}
    if getattr(args, "target_version", None):
        payload["target_version"] = args.target_version
    return _api_call("POST", f"/releases/{args.release_id}/rollback", base_url, api_key, json_body=payload)


def _cmd_release_verify(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("POST", f"/releases/{args.release_id}/verify", base_url, api_key, json_body={"verification_type": getattr(args, "verification_type", "smoke") or "smoke"})


def _cmd_release_history(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("GET", f"/releases/{args.release_id}/history", base_url, api_key)


# ---------------------------------------------------------------------------
# Flag subcommands
# ---------------------------------------------------------------------------

def _cmd_flag_create(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    payload: dict[str, Any] = {
        "key": args.key,
        "name": args.name or args.key,
        "flag_type": getattr(args, "flag_type", "boolean") or "boolean",
        "default_value": getattr(args, "default_value", "false") or "false",
        "description": getattr(args, "description", "") or "",
        "state": getattr(args, "state", "OFF") or "OFF",
        "owner": getattr(args, "owner", "system") or "system",
        "tags": getattr(args, "tags", []) or [],
    }
    if getattr(args, "expires_at", None):
        payload["expires_at"] = args.expires_at
    return _api_call("POST", "/feature-flags", base_url, api_key, json_body=payload)


def _cmd_flag_get(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("GET", f"/feature-flags/{args.key}", base_url, api_key)


def _cmd_flag_set(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    # PUT /feature-flags/{key}
    payload: dict[str, Any] = {}
    if getattr(args, "name", None):
        payload["name"] = args.name
    if getattr(args, "flag_type", None):
        payload["flag_type"] = args.flag_type
    if getattr(args, "default_value", None):
        payload["default_value"] = args.default_value
    if getattr(args, "state", None):
        payload["state"] = args.state
    if getattr(args, "description", None):
        payload["description"] = args.description
    if not payload:
        payload = {"state": "ON"}
    return _api_call("PUT", f"/feature-flags/{args.key}", base_url, api_key, json_body=payload)


def _cmd_flag_rollout(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    # POST /feature-flags/{key}/rules  with percentage
    payload: dict[str, Any] = {
        "rule_type": "percentage",
        "value": args.key,
        "percentage": int(args.percentage),
        "rank": int(getattr(args, "rank", 0) or 0),
    }
    return _api_call("POST", f"/feature-flags/{args.key}/rules", base_url, api_key, json_body=payload)


def _cmd_flag_archive(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    return _api_call("POST", f"/feature-flags/{args.key}/archive", base_url, api_key)


def _cmd_flag_evaluate(args: argparse.Namespace, base_url: str, api_key: Optional[str]) -> Any:
    context: dict[str, Any] = {}
    ctx_raw = getattr(args, "context", None)
    if ctx_raw:
        try:
            context = json.loads(ctx_raw) if isinstance(ctx_raw, str) else dict(ctx_raw)
        except Exception:
            # treat as key=value pairs
            for pair in str(ctx_raw).split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    context[k.strip()] = v.strip()
    # also support --user-id / --env etc shortcuts
    if getattr(args, "user_id", None):
        context["user_id"] = args.user_id
    if getattr(args, "env", None):
        context["env"] = args.env
    return _api_call("POST", f"/feature-flags/{args.key}/evaluate", base_url, api_key, json_body={"context": context})


RELEASE_DISPATCH = {
    "create": _cmd_release_create,
    "validate": _cmd_release_validate,
    "approve": _cmd_release_approve,
    "deploy": _cmd_release_deploy,
    "status": _cmd_release_status,
    "promote": _cmd_release_promote,
    "pause": _cmd_release_pause,
    "rollback": _cmd_release_rollback,
    "verify": _cmd_release_verify,
    "history": _cmd_release_history,
}

FLAG_DISPATCH = {
    "create": _cmd_flag_create,
    "get": _cmd_flag_get,
    "set": _cmd_flag_set,
    "rollout": _cmd_flag_rollout,
    "archive": _cmd_flag_archive,
    "evaluate": _cmd_flag_evaluate,
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_release_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova release", description="Release & Progressive Delivery CLI (Volume 56)")
    parser.add_argument("--base-url", default=None, help="Backend base URL (env NOVAFORGE_BASE_URL)")
    parser.add_argument("--api-key", default=None, help="API key (env NOVAFORGE_API_KEY)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    parser.add_argument("--ci", action="store_true", help="CI mode — compact JSON, errors as JSON on stderr")
    sub = parser.add_subparsers(dest="resource", help="release or flag")

    # ── release ─────────────────────────────────────────────────────────
    p_release = sub.add_parser("release", help="Release lifecycle commands")
    rsub = p_release.add_subparsers(dest="action", help="release action")

    # release create
    p_create = rsub.add_parser("create", help="Create a release")
    p_create.add_argument("--project", required=True, help="Project name")
    p_create.add_argument("--service", required=True, help="Service name")
    p_create.add_argument("--version", required=True, help="Version (semantic/build/commit/model/agent/plugin)")
    p_create.add_argument("--artifact-id", required=True, help="DeliveryArtifact UUID")
    p_create.add_argument("--environment", default="DEV", help="Environment (DEV/STAGING/CANARY/PRODUCTION)")
    p_create.add_argument("--release-channel", default="DEV", help="Release channel")
    p_create.add_argument("--strategy", default="rolling", choices=["rolling", "blue-green", "canary", "weighted", "shadow", "dark"], help="Rollout strategy")
    p_create.add_argument("--commit-sha", default=None, help="Commit SHA")
    p_create.add_argument("--build-id", default=None, help="Build ID")
    p_create.add_argument("--metadata", default=None, help="JSON metadata string")

    # release validate
    p_val = rsub.add_parser("validate", help="Validate a release")
    p_val.add_argument("release_id", help="Release ID")

    # release approve
    p_app = rsub.add_parser("approve", help="Approve a release")
    p_app.add_argument("release_id", help="Release ID")
    p_app.add_argument("--approver-role", default="reviewer", help="Approver role")
    p_app.add_argument("--decision", default="approved", choices=["approved", "rejected"], help="Decision")
    p_app.add_argument("--reason", default=None, help="Reason")
    p_app.add_argument("--signature", default=None, help="Signature")
    p_app.add_argument("--version", default=None, help="Version (must match release.version)")

    # release deploy
    p_dep = rsub.add_parser("deploy", help="Deploy a release (orchestrate)")
    p_dep.add_argument("release_id", help="Release ID")

    # release status
    p_stat = rsub.add_parser("status", help="Get release status")
    p_stat.add_argument("release_id", help="Release ID")

    # release promote
    p_prom = rsub.add_parser("promote", help="Promote release to target env")
    p_prom.add_argument("release_id", help="Release ID")
    p_prom.add_argument("--target-env", required=True, help="Target environment")

    # release pause
    p_pause = rsub.add_parser("pause", help="Pause a release/rollout")
    p_pause.add_argument("release_id", help="Release ID")
    p_pause.add_argument("--reason", default=None, help="Reason")

    # release rollback
    p_rb = rsub.add_parser("rollback", help="Rollback a release")
    p_rb.add_argument("release_id", help="Release ID")
    p_rb.add_argument("--reason", default="manual rollback", help="Reason")
    p_rb.add_argument("--target-version", default=None, help="Target version to rollback to")

    # release verify
    p_ver = rsub.add_parser("verify", help="Verify a release")
    p_ver.add_argument("release_id", help="Release ID")
    p_ver.add_argument("--verification-type", default="smoke", choices=["smoke", "health", "targeted", "synthetic"], help="Verification type")

    # history (not in top spec but useful, maps to release_history)
    p_hist = rsub.add_parser("history", help="Get release history")
    p_hist.add_argument("release_id", help="Release ID")

    # ── flag ────────────────────────────────────────────────────────────
    p_flag = sub.add_parser("flag", help="Feature flag commands")
    fsub = p_flag.add_subparsers(dest="action", help="flag action")

    # flag create
    p_fc = fsub.add_parser("create", help="Create a feature flag")
    p_fc.add_argument("--key", required=True, help="Flag key")
    p_fc.add_argument("--name", default=None, help="Human name")
    p_fc.add_argument("--flag-type", default="boolean", choices=["boolean", "percentage", "segment"], help="Flag type")
    p_fc.add_argument("--default-value", default="false", help="Default value")
    p_fc.add_argument("--description", default="", help="Description")
    p_fc.add_argument("--state", default="OFF", choices=["OFF", "ON", "ROLLOUT", "PAUSED", "ARCHIVED"], help="Initial state")
    p_fc.add_argument("--owner", default="system", help="Owner")
    p_fc.add_argument("--expires-at", default=None, help="Expiry ISO timestamp")
    p_fc.add_argument("--tags", nargs="*", default=[], help="Tags")

    # flag get
    p_fg = fsub.add_parser("get", help="Get a flag")
    p_fg.add_argument("key", help="Flag key")

    # flag set (update)
    p_fs = fsub.add_parser("set", help="Update a flag")
    p_fs.add_argument("key", help="Flag key")
    p_fs.add_argument("--name", default=None, help="Name")
    p_fs.add_argument("--flag-type", default=None, help="Type")
    p_fs.add_argument("--default-value", default=None, help="Default value")
    p_fs.add_argument("--state", default=None, help="State")
    p_fs.add_argument("--description", default=None, help="Description")

    # flag rollout
    p_fr = fsub.add_parser("rollout", help="Set percentage rollout")
    p_fr.add_argument("key", help="Flag key")
    p_fr.add_argument("percentage", type=int, help="Percentage 0-100")
    p_fr.add_argument("--rank", type=int, default=0, help="Rule rank")

    # flag archive
    p_fa = fsub.add_parser("archive", help="Archive a flag")
    p_fa.add_argument("key", help="Flag key")

    # flag evaluate
    p_fe = fsub.add_parser("evaluate", help="Evaluate a flag")
    p_fe.add_argument("key", help="Flag key")
    p_fe.add_argument("--context", default=None, help="JSON context string or key=value list")
    p_fe.add_argument("--user-id", default=None, help="User ID for bucketing")
    p_fe.add_argument("--env", default=None, help="Environment dimension")

    return parser


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def handle_release_command(args: Any) -> None:
    """Dispatch ``nova release ...`` and ``nova flag ...`` commands.

    Args:
        args: list[str] from CLI (e.g. sys.argv[1:]) or already-parsed Namespace.
              Supports ``--json`` and ``--ci`` global flags, calls API via httpx.
    """
    # Normalize to list[str] so both callers work
    if isinstance(args, argparse.Namespace):
        parsed = args
        # need base_url/api_key resolution from parsed
        base_url = _resolve_base_url(getattr(parsed, "base_url", None))
        api_key = _resolve_api_key(getattr(parsed, "api_key", None))
        as_json = bool(getattr(parsed, "as_json", False))
        ci = bool(getattr(parsed, "ci", False))
        resource = getattr(parsed, "resource", None)
        action = getattr(parsed, "action", None)
    else:
        # args is list[str] or None
        argv: list[str] = list(args) if args is not None else []
        # Allow callers to pass ["release", "create", ...] without the leading "nova"
        parser = build_release_parser()
        try:
            parsed = parser.parse_args(argv)
        except SystemExit as exc:
            # argparse calls sys.exit on error — let it propagate but handle help
            raise
        base_url = _resolve_base_url(getattr(parsed, "base_url", None))
        api_key = _resolve_api_key(getattr(parsed, "api_key", None))
        as_json = bool(getattr(parsed, "as_json", False))
        ci = bool(getattr(parsed, "ci", False))
        resource = getattr(parsed, "resource", None)
        action = getattr(parsed, "action", None)

    if not resource or not action:
        parser = build_release_parser()
        parser.print_help()
        return

    # dispatch table
    dispatch_map: dict[str, dict[str, Any]] = {
        "release": RELEASE_DISPATCH,
        "flag": FLAG_DISPATCH,
    }
    table = dispatch_map.get(resource)
    if table is None:
        _print_error(f"Unknown resource: {resource}", ci)
        if ci:
            print(json.dumps({"error": f"unknown resource {resource}"}))
        return
    handler = table.get(action)
    if handler is None:
        _print_error(f"Unknown {resource} action: {action}", ci)
        return

    try:
        result = handler(parsed, base_url, api_key)
        _print_result(result, as_json, ci)
        # in CI mode exit code 0 on success, non-zero is handled via exception
        if ci:
            # also ensure valid JSON on stdout for CI parsers
            pass
    except RuntimeError as exc:
        _print_error(str(exc), ci)
        if ci:
            print(json.dumps({"error": str(exc), "resource": resource, "action": action}, default=str))
            sys.exit(1)
        else:
            print(json.dumps({"error": str(exc)}, indent=2, default=str), file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        _print_error(str(exc), ci)
        if ci:
            print(json.dumps({"error": str(exc)}, default=str))
            sys.exit(1)
        raise


if __name__ == "__main__":
    handle_release_command(sys.argv[1:])
