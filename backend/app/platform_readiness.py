"""Production-readiness assessment — Volume 72 Commit 2.

Collects machine-readable readiness signals (migration head, commit,
route counts, worker/lease health, event registrations, dependency
probes, configuration posture) and derives a status of READY,
READY_WITH_WARNINGS or BLOCKED. Read-only: never mutates state.
"""

from __future__ import annotations

import ast
import glob
import json
import subprocess
from datetime import datetime, timezone
from typing import Any


def migration_head() -> dict:
    versions: dict[str, set] = {}
    for path in glob.glob("backend/alembic/versions/0*.py"):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        values: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                    node.targets[0], ast.Name) and node.targets[0].id in (
                    "revision", "down_revision"):
                try:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
                except Exception:
                    continue
        if "revision" not in values:
            continue
        revisions = values["revision"]
        revisions = revisions if isinstance(revisions, tuple) else (revisions,)
        downs = values.get("down_revision")
        downs = set(downs) if isinstance(downs, tuple) else ({downs} if downs else set())
        for revision in revisions:
            versions[revision] = downs
    children: dict[str, list] = {}
    for revision, downs in versions.items():
        for down in downs:
            children.setdefault(down, []).append(revision)
    heads = sorted(r for r in versions if not children.get(r))
    return {"heads": heads, "count": len(versions),
            "single_head": len(heads) == 1,
            "head": heads[0] if len(heads) == 1 else ""}


def commit_info() -> dict:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=15).stdout.strip()
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                                text=True, timeout=15).stdout.strip()
        status = subprocess.run(["git", "status", "--short"], capture_output=True,
                                text=True, timeout=15).stdout.strip()
        return {"sha": sha, "branch": branch, "clean": not bool(status)}
    except Exception as exc:
        return {"sha": "", "branch": "", "clean": False, "error": str(exc)}


def route_inventory() -> dict:
    from app.api.router import api_router

    def _iter(router, prefix=""):
        out = []
        for route in router.routes:
            if type(route).__name__ == "_IncludedRouter":
                ctx = route.include_context
                out += _iter(route.original_router, getattr(ctx, "prefix", "") or "")
            else:
                methods = sorted(getattr(route, "methods", None) or [])
                path = getattr(route, "path", "") or ""
                if methods and path:
                    out.append((tuple(methods), prefix + path))
        return out

    routes = [(m, p) for m, p in _iter(api_router) if p.startswith("/api/")]
    import re
    seen: dict[tuple, int] = {}
    for methods, path in routes:
        for method in methods:
            # Literal comparison: trailing-slash twins ("/x" + hidden "/x/")
            # are intentional compat shims, not conflicts. Parameter names
            # are normalized since Starlette matches them identically.
            normalized = re.sub(r"\{[^}]+\}", "{}", path)
            key = (method, normalized)
            seen[key] = seen.get(key, 0) + 1
    duplicates = {k: v for k, v in seen.items() if v > 1}
    doubled = sorted({p for _, p in routes
                      if "/api/v1/api/" in p or "ai-governance/ai-governance" in p
                      or "kernel/kernel" in p})
    return {"total": len(routes), "duplicates": duplicates,
            "doubled_prefixes": doubled}


def worker_status() -> dict:
    import app.ai_dev.workers as _aiw
    import app.finops.governed_workers as _fw
    import app.governance.plane_workers as _gw
    import app.integrations.workers as _iw
    import app.knowledge.workers as _kw
    import app.workflow.recovery as _wr
    return {
        "ai_dev": {"leases": len(_aiw._agent_leases)},
        "finops": {"leases": len(_fw._aggregation_leases)},
        "governance": {"leases": len(_gw._leases)},
        "integrations": {"leases": len(_iw._leases)},
        "knowledge": {"leases": len(_kw._ingestion_leases)},
        "workflow": {"leases": len(_wr._lease_store)},
    }


def event_status() -> dict:
    from app.core.events import EventType
    names = [m.name for m in EventType]
    return {"total": len(names), "unique_names": len(set(names))}


def dependency_health() -> dict:
    health: dict[str, Any] = {}
    try:
        from app.core.config import settings
        health["cors_origins"] = list(settings.cors_origins or [])
        health["debug"] = bool(getattr(settings, "debug", False))
        health["redis_url_configured"] = bool(getattr(settings, "redis_url", ""))
        health["database_configured"] = bool(getattr(settings, "database_url", ""))
    except Exception as exc:
        health["config_error"] = str(exc)
    return health


def collect_readiness() -> dict:
    migration = migration_head()
    commit = commit_info()
    routes = route_inventory()
    workers = worker_status()
    events = event_status()
    deps = dependency_health()
    blockers: list[str] = []
    warnings: list[str] = []
    if not migration["single_head"]:
        blockers.append(f"migration heads: {migration['heads']}")
    if routes["duplicates"]:
        blockers.append(f"duplicate routes: {sorted(routes['duplicates'])[:5]}")
    if routes["doubled_prefixes"]:
        blockers.append(f"doubled prefixes: {routes['doubled_prefixes'][:5]}")
    if events["total"] != events["unique_names"]:
        blockers.append("duplicate EventType member names")
    if not commit["clean"]:
        warnings.append("working tree has uncommitted changes")
    if deps.get("debug"):
        warnings.append("debug mode enabled")
    status = "BLOCKED" if blockers else ("READY_WITH_WARNINGS" if warnings else "READY")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "migration": migration,
        "commit": commit,
        "routes": {"total": routes["total"]},
        "workers": workers,
        "events": events,
        "dependencies": deps,
        "blockers": blockers,
        "warnings": warnings,
        "status": status,
        "known_limitations": [
            "process-local worker leases are single-replica (regions orchestrator uses DB fencing)",
            "legacy file-backed governance managers retained read-only for bridging",
            "SQLite test parity shim for JSONB; PostgreSQL authoritative in production",
        ],
    }


def write_report(directory: str) -> dict:
    import os
    report = collect_readiness()
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "readiness_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    lines = [
        "# NovaForge Backend Readiness Report", "",
        f"Generated: {report['generated_at']}", f"Status: **{report['status']}**", "",
        f"Migration head: `{report['migration']['head']}` "
        f"({'single' if report['migration']['single_head'] else 'MULTIPLE HEADS'})",
        f"Commit: `{report['commit'].get('sha', '')[:12]}` "
        f"({'clean' if report['commit'].get('clean') else 'dirty'})",
        f"Routes: {report['routes']['total']}",
        f"Events: {report['events']['total']} (unique names: {report['events']['unique_names']})", "",
        "## Blockers",
        *([f"- {b}" for b in report["blockers"]] or ["- none"]),
        "", "## Warnings",
        *([f"- {w}" for w in report["warnings"]] or ["- none"]),
        "", "## Known limitations",
        *[f"- {lim}" for lim in report["known_limitations"]], "",
    ]
    with open(os.path.join(directory, "readiness_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return report
