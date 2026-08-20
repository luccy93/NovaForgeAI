"""AI Software Quality Engine -- Quality Baselines (Volume 48).

Create, capture, compare, and diff quality baselines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class BaselineSnapshot:
    quality_scores: dict[str, float] = field(default_factory=dict)
    finding_counts: dict[str, int] = field(default_factory=dict)
    total_findings: int = 0
    risk_score: float = 0.0
    gate_pass: bool = True
    timestamp: str = ""
    review_id: str = ""


@dataclass
class BaselineDiff:
    baseline_name: str
    current_name: str
    score_deltas: dict[str, float] = field(default_factory=dict)
    finding_delta: int = 0
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    summary: str = ""


class BaselineService:
    """In-memory baseline manager for quality snapshots."""

    def __init__(self):
        self._baselines: dict[str, dict[str, Any]] = {}

    def create(
        self,
        tenant: str,
        repo_id: str,
        name: str,
        snapshot: dict[str, Any],
        description: str = "",
        prompt_version: str = "1.0",
        created_by: str = "user",
    ) -> dict[str, Any]:
        baseline_id = str(uuid4())
        baseline = {
            "id": baseline_id,
            "tenant": tenant,
            "repo_id": repo_id,
            "name": name,
            "description": description,
            "snapshot": snapshot,
            "prompt_version": prompt_version,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        key = f"{tenant}:{repo_id}:{name}"
        self._baselines[key] = baseline
        return baseline

    def get(self, tenant: str, repo_id: str, name: str = "default") -> dict[str, Any] | None:
        return self._baselines.get(f"{tenant}:{repo_id}:{name}")

    def list_baselines(self, tenant: str, repo_id: str = "") -> list[dict[str, Any]]:
        results = []
        for key, b in self._baselines.items():
            if b["tenant"] == tenant and (not repo_id or b["repo_id"] == repo_id):
                results.append(b)
        return results

    def delete(self, tenant: str, repo_id: str, name: str) -> bool:
        key = f"{tenant}:{repo_id}:{name}"
        if key in self._baselines:
            del self._baselines[key]
            return True
        return False

    def diff(
        self,
        baseline: dict[str, Any],
        current: dict[str, Any],
    ) -> BaselineDiff:
        base_scores = baseline.get("snapshot", {}).get("quality_scores", {})
        curr_scores = current.get("snapshot", {}).get("quality_scores", {})
        base_findings = baseline.get("snapshot", {}).get("total_findings", 0)
        curr_findings = current.get("snapshot", {}).get("total_findings", 0)

        score_deltas: dict[str, float] = {}
        regressions: list[str] = []
        improvements: list[str] = []

        all_dims = set(base_scores.keys()) | set(curr_scores.keys())
        for dim in all_dims:
            base_val = base_scores.get(dim, 0.0)
            curr_val = curr_scores.get(dim, 0.0)
            delta = round(curr_val - base_val, 4)
            score_deltas[dim] = delta
            if delta < -0.05:
                regressions.append(f"{dim}: {base_val:.3f} -> {curr_val:.3f} (delta: {delta:+.3f})")
            elif delta > 0.05:
                improvements.append(f"{dim}: {base_val:.3f} -> {curr_val:.3f} (delta: {delta:+.3f})")

        finding_delta = curr_findings - base_findings
        if finding_delta > 0:
            regressions.append(f"Findings increased: {base_findings} -> {curr_findings}")
        elif finding_delta < 0:
            improvements.append(f"Findings decreased: {base_findings} -> {curr_findings}")

        parts = []
        if regressions:
            parts.append(f"{len(regressions)} regressions")
        if improvements:
            parts.append(f"{len(improvements)} improvements")
        summary = "; ".join(parts) if parts else "No significant changes"

        return BaselineDiff(
            baseline_name=baseline.get("name", ""),
            current_name=current.get("name", "current"),
            score_deltas=score_deltas,
            finding_delta=finding_delta,
            regressions=regressions,
            improvements=improvements,
            summary=summary,
        )
