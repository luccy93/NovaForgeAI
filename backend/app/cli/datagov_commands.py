"""Data Governance CLI — Volume 57.

``nova governance assets|classify|lineage|retention|requests|export|policy|controls|evidence|dlp``
with ``--json`` output. Talks to the governance REST API over HTTP.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import httpx


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


def _headers(api_key: Optional[str]) -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
        h["X-API-Key"] = api_key
    return h


def _api(method: str, path: str, base_url: str, api_key: Optional[str], body: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    url = f"{base_url}/api/v1{path}" if not path.startswith("/api") else f"{base_url}{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, headers=_headers(api_key), json=body, params=params)
            resp.raise_for_status()
            if resp.content:
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}
            return {"status_code": resp.status_code}
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}")
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Cannot connect to {base_url}: {exc}")


def _out(data: Any, as_json: bool) -> None:
    print(json.dumps(data, indent=None if as_json else 2, default=str))


# ── subcommand handlers ────────────────────────────────────────────────


def _cmd_assets(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "list":
        params = {}
        if a.classification:
            params["classification"] = a.classification
        return _api("GET", "/governance/assets", base, key, params=params)
    if a.action == "discover":
        return _api("POST", "/governance/assets/discover", base, key, body={})
    if a.action == "get":
        return _api("GET", f"/governance/assets/{a.asset_id}", base, key)
    if a.action == "register":
        body = {
            "asset_id": a.asset_id, "resource": a.resource, "type": a.type,
            "owner": getattr(a, "owner", None), "source": getattr(a, "source", None),
            "location": getattr(a, "location", None),
        }
        if getattr(a, "workspace", None):
            body["workspace"] = a.workspace
        if getattr(a, "project", None):
            body["project"] = a.project
        return _api("POST", "/governance/assets", base, key, body=body)
    raise SystemExit(f"unknown assets action: {a.action}")


def _cmd_classify(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.sub == "detect":
        return _api("POST", "/governance/classify/detect", base, key, body={"text": a.text})
    if a.sub == "auto":
        return _api("POST", "/governance/classify/auto", base, key, body={"asset_id": a.asset_id, "content_sample": a.text})
    return _api("POST", f"/governance/assets/{a.asset_id}/classify", base, key, body={
        "level": a.level, "source": a.source, "evidence": {"via": "cli"},
    })


def _cmd_lineage(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "record":
        return _api("POST", "/governance/lineage", base, key, body={
            "source_asset": a.source, "target_asset": a.target,
            "transformation": a.transformation, "evidence": a.evidence, "stage": a.stage,
        })
    if a.action == "upstream":
        return _api("GET", f"/governance/lineage/{a.asset_id}/upstream", base, key)
    if a.action == "downstream":
        return _api("GET", f"/governance/lineage/{a.asset_id}/downstream", base, key)
    if a.action == "impact":
        return _api("GET", f"/governance/lineage/{a.asset_id}/impact", base, key)
    raise SystemExit(f"unknown lineage action: {a.action}")


def _cmd_retention(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "policies":
        return _api("GET", "/governance/retention/policies", base, key)
    if a.action == "create-policy":
        return _api("POST", "/governance/retention/policies", base, key, body={
            "resource": getattr(a, "resource", None), "classification": getattr(a, "classification", None),
            "data_type": getattr(a, "data_type", None), "environment": getattr(a, "environment", None),
            "retention_days": a.days, "action": a.r_action,
        })
    if a.action == "check":
        return _api("GET", "/governance/retention/check", base, key)
    if a.action == "hold":
        return _api("POST", "/governance/legal-holds", base, key, body={"scope": a.scope, "reason": a.reason})
    if a.action == "holds":
        return _api("GET", "/governance/legal-holds", base, key)
    if a.action == "release":
        return _api("DELETE", f"/governance/legal-holds/{a.hold_id}", base, key)
    raise SystemExit(f"unknown retention action: {a.action}")


def _cmd_requests(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "create":
        return _api("POST", "/governance/requests", base, key, body={
            "request_type": a.request_type, "subject": a.subject, "scope": {},
        })
    if a.action == "list":
        return _api("GET", "/governance/requests", base, key)
    if a.action == "verify":
        return _api("POST", f"/governance/requests/{a.request_id}/verify", base, key, body={"method": a.method})
    if a.action == "approve":
        return _api("POST", f"/governance/requests/{a.request_id}/approve", base, key, body={"decision": a.decision})
    if a.action == "complete":
        return _api("POST", f"/governance/requests/{a.request_id}/complete", base, key, body={"systems": [], "completion": {}})
    if a.action == "export":
        return _api("POST", "/governance/exports", base, key, body={
            "scope": {"request_id": a.request_id}, "data_sources": [], "format": "json",
        })
    raise SystemExit(f"unknown requests action: {a.action}")


def _cmd_export(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "create":
        return _api("POST", "/governance/exports", base, key, body={
            "scope": {}, "data_sources": (a.sources.split(",") if a.sources else []), "format": a.format,
        })
    if a.action == "get":
        return _api("GET", f"/governance/exports/{a.export_id}", base, key)
    if a.action == "verify":
        return _api("POST", f"/governance/exports/{a.export_id}/verify", base, key, body={"token": a.token})
    if a.action == "revoke":
        return _api("POST", f"/governance/exports/{a.export_id}/revoke", base, key, body={})
    raise SystemExit(f"unknown export action: {a.action}")


def _cmd_policy(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "evaluate":
        return _api("POST", "/governance/policies/evaluate", base, key, body={
            "resource": a.resource, "policy_type": a.policy_type,
            "context": json.loads(a.context) if a.context else {},
        })
    if a.action == "simulate":
        return _api("POST", "/governance/policies/simulate", base, key, body={
            "resource": a.resource, "context": json.loads(a.context) if a.context else {},
        })
    if a.action == "decisions":
        return _api("GET", "/governance/policies/decisions", base, key)
    raise SystemExit(f"unknown policy action: {a.action}")


def _cmd_controls(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "list":
        return _api("GET", "/governance/controls", base, key)
    if a.action == "create":
        return _api("POST", "/governance/controls", base, key, body={
            "framework": a.framework, "control_id": a.control_id, "owner": getattr(a, "owner", None),
        })
    if a.action == "assess":
        return _api("POST", f"/governance/controls/{a.control_id}/assess", base, key, body={"status": a.status})
    if a.action == "package":
        return _api("GET", "/governance/controls/package", base, key, params={"framework": a.framework})
    raise SystemExit(f"unknown controls action: {a.action}")


def _cmd_evidence(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "collect":
        return _api("POST", f"/governance/controls/{a.control_id}/evidence", base, key, body={
            "evidence_type": a.evidence_type, "source": a.source, "valid_until": getattr(a, "valid_until", None),
        })
    if a.action == "list":
        return _api("GET", f"/governance/controls/{a.control_id}/evidence", base, key)
    raise SystemExit(f"unknown evidence action: {a.action}")


def _cmd_dlp(a: argparse.Namespace, base: str, key: Optional[str]) -> Any:
    if a.action == "scan":
        return _api("POST", "/governance/dlp/scan", base, key, body={
            "destination": a.destination, "content_sample": a.text, "classification": a.classification,
        })
    if a.action == "events":
        return _api("GET", "/governance/dlp/events", base, key)
    if a.action == "redact":
        return _api("POST", "/governance/dlp/redact", base, key, body={"text": a.text, "classification": a.classification})
    raise SystemExit(f"unknown dlp action: {a.action}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nova governance", description="Data Governance CLI (Volume 57)")
    p.add_argument("--base-url", default=None)
    p.add_argument("--api-key", default=None)
    p.add_argument("--json", dest="as_json", action="store_true")
    sub = p.add_subparsers(dest="module", required=True)

    sp = sub.add_parser("assets"); asub = sp.add_subparsers(dest="action", required=True)
    s = asub.add_parser("list"); s.add_argument("--classification", default=None)
    s = asub.add_parser("discover")
    s = asub.add_parser("get"); s.add_argument("asset_id")
    s = asub.add_parser("register"); s.add_argument("asset_id"); s.add_argument("resource"); s.add_argument("type")
    s.add_argument("--owner", default=None); s.add_argument("--source", default=None)
    s.add_argument("--location", default=None); s.add_argument("--workspace", default=None); s.add_argument("--project", default=None)

    sp = sub.add_parser("classify"); csub = sp.add_subparsers(dest="sub", required=True)
    s = csub.add_parser("set"); s.add_argument("asset_id"); s.add_argument("level")
    s.add_argument("--source", default="user")
    s = csub.add_parser("auto"); s.add_argument("asset_id"); s.add_argument("--text", required=True)
    s = csub.add_parser("detect"); s.add_argument("--text", required=True)

    sp = sub.add_parser("lineage"); lsub = sp.add_subparsers(dest="action", required=True)
    s = lsub.add_parser("record"); s.add_argument("--source", required=True); s.add_argument("--target", required=True)
    s.add_argument("--transformation", required=True); s.add_argument("--evidence", required=True); s.add_argument("--stage", default="transform")
    for act in ("upstream", "downstream", "impact"):
        s = lsub.add_parser(act); s.add_argument("asset_id")

    sp = sub.add_parser("retention"); rsub = sp.add_subparsers(dest="action", required=True)
    s = rsub.add_parser("policies")
    s = rsub.add_parser("create-policy"); s.add_argument("--days", type=int, required=True)
    s.add_argument("--resource", default=None); s.add_argument("--classification", default=None)
    s.add_argument("--data-type", default=None); s.add_argument("--environment", default=None)
    s.add_argument("--action", dest="r_action", default="delete")
    s = rsub.add_parser("check")
    s = rsub.add_parser("hold"); s.add_argument("--scope", required=True); s.add_argument("--reason", required=True)
    s = rsub.add_parser("holds")
    s = rsub.add_parser("release"); s.add_argument("hold_id")

    sp = sub.add_parser("requests"); qsub = sp.add_subparsers(dest="action", required=True)
    s = qsub.add_parser("create"); s.add_argument("--type", dest="request_type", required=True); s.add_argument("--subject", required=True)
    s = qsub.add_parser("list")
    s = qsub.add_parser("verify"); s.add_argument("request_id"); s.add_argument("--method", default="mfa")
    s = qsub.add_parser("approve"); s.add_argument("request_id"); s.add_argument("--decision", default="approved")
    s = qsub.add_parser("complete"); s.add_argument("request_id")
    s = qsub.add_parser("export"); s.add_argument("request_id")

    sp = sub.add_parser("export"); esub = sp.add_subparsers(dest="action", required=True)
    s = esub.add_parser("create"); s.add_argument("--sources", default=None); s.add_argument("--format", default="json")
    s = esub.add_parser("get"); s.add_argument("export_id")
    s = esub.add_parser("verify"); s.add_argument("export_id"); s.add_argument("token")
    s = esub.add_parser("revoke"); s.add_argument("export_id")

    sp = sub.add_parser("policy"); psub = sp.add_subparsers(dest="action", required=True)
    s = psub.add_parser("evaluate"); s.add_argument("--resource", required=True); s.add_argument("--policy-type", default="data_retention")
    s.add_argument("--context", default=None)
    s = psub.add_parser("simulate"); s.add_argument("--resource", required=True); s.add_argument("--context", default=None)
    s = psub.add_parser("decisions")

    sp = sub.add_parser("controls"); ksub = sp.add_subparsers(dest="action", required=True)
    s = ksub.add_parser("list")
    s = ksub.add_parser("create"); s.add_argument("--framework", required=True); s.add_argument("--control-id", required=True)
    s.add_argument("--owner", default=None)
    s = ksub.add_parser("assess"); s.add_argument("control_id"); s.add_argument("--status", required=True)
    s = ksub.add_parser("package"); s.add_argument("--framework", required=True)

    sp = sub.add_parser("evidence"); vsub = sp.add_subparsers(dest="action", required=True)
    s = vsub.add_parser("collect"); s.add_argument("control_id"); s.add_argument("--evidence-type", required=True)
    s.add_argument("--source", required=True); s.add_argument("--valid-until", default=None)
    s = vsub.add_parser("list"); s.add_argument("control_id")

    sp = sub.add_parser("dlp"); dsub = sp.add_subparsers(dest="action", required=True)
    s = dsub.add_parser("scan"); s.add_argument("--destination", required=True); s.add_argument("--text", required=True)
    s.add_argument("--classification", default="INTERNAL")
    s = dsub.add_parser("events")
    s = dsub.add_parser("redact"); s.add_argument("--text", required=True); s.add_argument("--classification", default="RESTRICTED")

    return p


def handle_datagov_command(argv: list | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    base = _resolve_base_url(getattr(args, "base_url", None))
    key = _resolve_api_key(getattr(args, "api_key", None))
    handlers = {
        "assets": _cmd_assets, "classify": _cmd_classify, "lineage": _cmd_lineage,
        "retention": _cmd_retention, "requests": _cmd_requests, "export": _cmd_export,
        "policy": _cmd_policy, "controls": _cmd_controls, "evidence": _cmd_evidence,
        "dlp": _cmd_dlp,
    }
    handler = handlers[args.module]
    try:
        result = handler(args, base, key)
        _out(result, bool(getattr(args, "as_json", False)))
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    handle_datagov_command()
