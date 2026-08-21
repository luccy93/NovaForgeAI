"""Unified Analytics Platform -- Engineering Intelligence / DORA Metrics (Volume 50).

In-memory engineering analytics: deployments, lead time, pull requests,
CI pipeline runs, and the four key DORA metrics.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _in_window(dt: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if dt is None:
        return True
    if start is not None and dt < start:
        return False
    if end is not None and dt > end:
        return False
    return True


def _median(values) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (float(ordered[mid - 1]) + float(ordered[mid])) / 2.0


def _percentile(values, pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


def _mean(values) -> float:
    return sum(values) / len(values) if values else 0.0


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


class EngineeringService:
    """In-memory DORA / engineering intelligence store."""

    def __init__(self) -> None:
        self._deployments: list[dict] = []
        self._lead_time_events: list[dict] = []
        self._pr_events: list[dict] = []
        self._ci_runs: list[dict] = []

    # ── Recording ─────────────────────────────────────────────────────

    def record_deployment(self, tenant: str, service: str, commit_sha: str = "",
                          environment: str = "production", deployed_at: str = "",
                          success: bool = True, rollback: bool = False,
                          metadata: dict = None) -> dict:
        ts = _parse_ts(deployed_at) or _utcnow()
        meta = dict(metadata or {})
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "service": service,
            "commit_sha": commit_sha,
            "environment": environment,
            "deployed_at": _iso(ts),
            "_dt": ts,
            "success": bool(success),
            "rollback": bool(rollback),
            "failed": (not success) or bool(rollback),
            "team": str(meta.get("team", "")),
            "project": str(meta.get("project", "")),
            "repository": str(meta.get("repository", "")),
            "metadata": meta,
            "metadata_json": json.dumps(meta, sort_keys=True, default=str),
        }
        self._deployments.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_lead_time_event(self, tenant: str, repository: str, commit_sha: str = "",
                               commit_time: str = "", deploy_time: str = "") -> dict:
        commit_dt = _parse_ts(commit_time)
        deploy_dt = _parse_ts(deploy_time) or _utcnow()
        lead_minutes = None
        if commit_dt is not None:
            lead_minutes = max(0.0, (deploy_dt - commit_dt).total_seconds() / 60.0)
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "repository": repository,
            "commit_sha": commit_sha,
            "commit_time": _iso(commit_dt) if commit_dt else "",
            "deploy_time": _iso(deploy_dt),
            "_dt": deploy_dt,
            "lead_time_minutes": round(lead_minutes, 4) if lead_minutes is not None else None,
            "resolved": lead_minutes is not None,
        }
        self._lead_time_events.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_pr_event(self, tenant: str, repository: str, pr_id: str = "",
                        status: str = "merged", created_at: str = "", merged_at: str = "",
                        review_time_minutes: float = 0) -> dict:
        created_dt = _parse_ts(created_at)
        merged_dt = _parse_ts(merged_at) or (_utcnow() if status == "merged" else None)
        cycle_minutes = None
        if created_dt is not None and merged_dt is not None:
            cycle_minutes = max(0.0, (merged_dt - created_dt).total_seconds() / 60.0)
        review = float(review_time_minutes or 0)
        merge_minutes = None
        if cycle_minutes is not None:
            merge_minutes = max(0.0, cycle_minutes - review)
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "repository": repository,
            "pr_id": pr_id,
            "status": status,
            "created_at": _iso(created_dt) if created_dt else "",
            "merged_at": _iso(merged_dt) if merged_dt else "",
            "_dt": merged_dt or created_dt or _utcnow(),
            "review_time_minutes": round(review, 4),
            "cycle_time_minutes": round(cycle_minutes, 4) if cycle_minutes is not None else None,
            "merge_time_minutes": round(merge_minutes, 4) if merge_minutes is not None else None,
            "merged": status == "merged",
        }
        self._pr_events.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_ci_run(self, tenant: str, pipeline: str = "", status: str = "success",
                      queue_time_ms: float = 0, build_duration_ms: float = 0,
                      test_duration_ms: float = 0, started_at: str = "",
                      branch: str = "", commit_sha: str = "") -> dict:
        ts = _parse_ts(started_at) or _utcnow()
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "pipeline": pipeline,
            "status": status,
            "success": str(status).lower() == "success",
            "queue_time_ms": float(queue_time_ms or 0),
            "build_duration_ms": float(build_duration_ms or 0),
            "test_duration_ms": float(test_duration_ms or 0),
            "total_duration_ms": float(queue_time_ms or 0) + float(build_duration_ms or 0) + float(test_duration_ms or 0),
            "branch": branch,
            "commit_sha": commit_sha,
            "started_at": _iso(ts),
            "_dt": ts,
        }
        self._ci_runs.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    # ── Filtering helpers ─────────────────────────────────────────────

    def _window_deployments(self, tenant: str, start: str = "", end: str = "",
                            project: str = "", repository: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start), _parse_ts(end)
        return [
            d for d in self._deployments
            if d["tenant"] == tenant
            and _in_window(d["_dt"], start_dt, end_dt)
            and (not project or d["project"] == project)
            and (not repository or d["service"] == repository or d["repository"] == repository)
        ]

    def _window_lead_times(self, tenant: str, start: str = "", end: str = "",
                           repository: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start), _parse_ts(end)
        return [
            e for e in self._lead_time_events
            if e["tenant"] == tenant
            and _in_window(e["_dt"], start_dt, end_dt)
            and (not repository or e["repository"] == repository)
        ]

    def _window_prs(self, tenant: str, start: str = "", end: str = "",
                    repository: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start), _parse_ts(end)
        return [
            p for p in self._pr_events
            if p["tenant"] == tenant
            and _in_window(p["_dt"], start_dt, end_dt)
            and (not repository or p["repository"] == repository)
        ]

    def _window_ci_runs(self, tenant: str, start: str = "", end: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start), _parse_ts(end)
        return [
            r for r in self._ci_runs
            if r["tenant"] == tenant and _in_window(r["_dt"], start_dt, end_dt)
        ]

    @staticmethod
    def _mttr_minutes(deployments: list[dict]) -> float:
        ordered = sorted(
            (d for d in deployments if d["_dt"] is not None),
            key=lambda d: d["_dt"],
        )
        recoveries: list[float] = []
        for index, dep in enumerate(ordered):
            if not dep["failed"]:
                continue
            for later in ordered[index + 1:]:
                if later["service"] != dep["service"]:
                    continue
                if not later["failed"]:
                    recoveries.append((later["_dt"] - dep["_dt"]).total_seconds() / 60.0)
                    break
        return round(_mean(recoveries), 4)

    # ── DORA ──────────────────────────────────────────────────────────

    def compute_dora(self, tenant: str, project: str = "", repository: str = "",
                     start_time: str = "", end_time: str = "") -> dict:
        deployments = self._window_deployments(tenant, start_time, end_time, project, repository)
        lead_events = [
            e for e in self._window_lead_times(tenant, start_time, end_time, repository)
            if e["resolved"]
        ]
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        stamps = [d["_dt"] for d in deployments if d["_dt"] is not None]
        if start_dt and end_dt:
            span_days = max(1.0, (end_dt - start_dt).total_seconds() / 86400.0)
        elif stamps:
            span_days = max(1.0, ((max(stamps) - min(stamps)).total_seconds() + 86400.0) / 86400.0)
        else:
            span_days = 1.0
        failed = sum(1 for d in deployments if d["failed"])
        return {
            "deployment_frequency": round(len(deployments) / span_days, 4),
            "lead_time_minutes": round(_median([e["lead_time_minutes"] for e in lead_events]), 4),
            "change_failure_rate": _rate(failed, len(deployments)),
            "mttr_minutes": self._mttr_minutes(deployments),
        }

    def get_deployment_frequency(self, tenant: str, period: str = "day", project: str = "",
                                 start_time: str = "", end_time: str = "") -> float:
        deployments = self._window_deployments(tenant, start_time, end_time, project)
        period_days = {"day": 1.0, "week": 7.0, "month": 30.0}.get(str(period).lower(), 1.0)
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        if start_dt and end_dt:
            span_days = max(period_days, (end_dt - start_dt).total_seconds() / 86400.0)
        else:
            span_days = period_days
        return round(len(deployments) / (span_days / period_days), 4)

    def get_lead_time(self, tenant: str, project: str = "", start_time: str = "",
                      end_time: str = "") -> dict:
        events = [
            e for e in self._window_lead_times(tenant, start_time, end_time)
            if e["resolved"]
        ]
        if project:
            linked_services = {
                d["commit_sha"] for d in self._window_deployments(tenant, start_time, end_time, project)
                if d["commit_sha"]
            }
            events = [
                e for e in events
                if not linked_services or e["commit_sha"] in linked_services
            ]
        values = [e["lead_time_minutes"] for e in events]
        return {
            "median_minutes": round(_median(values), 4),
            "p90_minutes": round(_percentile(values, 90), 4),
            "p95_minutes": round(_percentile(values, 95), 4),
            "count": len(values),
        }

    def get_change_failure_rate(self, tenant: str, start_time: str = "",
                                end_time: str = "") -> float:
        deployments = self._window_deployments(tenant, start_time, end_time)
        failed = sum(1 for d in deployments if d["failed"])
        return _rate(failed, len(deployments))

    # ── Pull requests ─────────────────────────────────────────────────

    def get_pr_metrics(self, tenant: str, repository: str = "", start_time: str = "",
                       end_time: str = "") -> dict:
        prs = self._window_prs(tenant, start_time, end_time, repository)
        cycles = [p["cycle_time_minutes"] for p in prs if p["cycle_time_minutes"] is not None]
        reviews = [p["review_time_minutes"] for p in prs]
        merges = [p["merge_time_minutes"] for p in prs if p["merge_time_minutes"] is not None]
        merged = sum(1 for p in prs if p["merged"])
        return {
            "cycle_time_minutes": round(_median(cycles), 4),
            "review_time_minutes": round(_median(reviews), 4),
            "merge_time_minutes": round(_median(merges), 4),
            "total_prs": len(prs),
            "merged_prs": merged,
            "merge_rate": _rate(merged, len(prs)),
        }

    # ── Team / service views ──────────────────────────────────────────

    def get_team_metrics(self, tenant: str, team: str = "", start_time: str = "",
                         end_time: str = "") -> dict:
        deployments = [
            d for d in self._window_deployments(tenant, start_time, end_time)
            if not team or d["team"] == team
        ]
        repositories = sorted({d["repository"] or d["service"] for d in deployments} - {""})
        repo_set = set(repositories)
        lead_events = [
            e for e in self._window_lead_times(tenant, start_time, end_time)
            if e["resolved"] and (not repo_set or e["repository"] in repo_set)
        ]
        prs = [
            p for p in self._window_prs(tenant, start_time, end_time)
            if not repo_set or p["repository"] in repo_set
        ]
        cycles = [p["cycle_time_minutes"] for p in prs if p["cycle_time_minutes"] is not None]
        failed = sum(1 for d in deployments if d["failed"])
        succeeded = sum(1 for d in deployments if d["success"] and not d["rollback"])
        return {
            "team": team,
            "deployments": len(deployments),
            "successful_deployments": succeeded,
            "change_failure_rate": _rate(failed, len(deployments)),
            "deployment_success_rate": _rate(succeeded, len(deployments)),
            "lead_time_minutes": round(_median([e["lead_time_minutes"] for e in lead_events]), 4),
            "mttr_minutes": self._mttr_minutes(deployments),
            "prs_merged": sum(1 for p in prs if p["merged"]),
            "cycle_time_minutes": round(_median(cycles), 4),
            "repositories": repositories,
        }

    def get_service_metrics(self, tenant: str, service: str = "", start_time: str = "",
                            end_time: str = "") -> dict:
        deployments = [
            d for d in self._window_deployments(tenant, start_time, end_time)
            if not service or d["service"] == service
        ]
        shas = {d["commit_sha"] for d in deployments if d["commit_sha"]}
        lead_events = [
            e for e in self._window_lead_times(tenant, start_time, end_time)
            if e["resolved"] and (not shas or e["commit_sha"] in shas)
        ]
        failed = sum(1 for d in deployments if d["failed"])
        rollbacks = sum(1 for d in deployments if d["rollback"])
        succeeded = sum(1 for d in deployments if d["success"] and not d["rollback"])
        last_deploy = max((d["deployed_at"] for d in deployments), default="")
        environments = sorted({d["environment"] for d in deployments})
        return {
            "service": service,
            "deployments": len(deployments),
            "deployment_success_rate": _rate(succeeded, len(deployments)),
            "failures": failed,
            "rollbacks": rollbacks,
            "change_failure_rate": _rate(failed, len(deployments)),
            "mttr_minutes": self._mttr_minutes(deployments),
            "lead_time_minutes": round(_median([e["lead_time_minutes"] for e in lead_events]), 4),
            "environments": environments,
            "last_deployed_at": last_deploy,
        }

    # ── CI analytics ──────────────────────────────────────────────────

    def get_ci_analytics(self, tenant: str, start_time: str = "", end_time: str = "") -> dict:
        runs = self._window_ci_runs(tenant, start_time, end_time)
        succeeded = sum(1 for r in runs if r["success"])
        pipelines = sorted({r["pipeline"] for r in runs} - {""})
        return {
            "total_runs": len(runs),
            "successful_runs": succeeded,
            "failed_runs": len(runs) - succeeded,
            "pipeline_success_rate": _rate(succeeded, len(runs)),
            "avg_queue_time_ms": round(_mean([r["queue_time_ms"] for r in runs]), 4),
            "avg_build_duration_ms": round(_mean([r["build_duration_ms"] for r in runs]), 4),
            "avg_test_duration_ms": round(_mean([r["test_duration_ms"] for r in runs]), 4),
            "avg_total_duration_ms": round(_mean([r["total_duration_ms"] for r in runs]), 4),
            "pipelines": pipelines,
        }


engineering_service = EngineeringService()
