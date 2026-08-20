"""AI Software Quality Engine -- Historical Analysis (Volume 48).

Tracks recurring defects, hotspots, frequently reverted areas,
and high-change modules using git history patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Hotspot:
    file_path: str
    change_count: int = 0
    defect_count: int = 0
    risk_score: float = 0.0
    authors: list[str] = field(default_factory=list)
    last_changed: str = ""


@dataclass
class TrendPoint:
    timestamp: str
    scores: dict[str, float] = field(default_factory=dict)
    finding_counts: dict[str, int] = field(default_factory=dict)
    total_findings: int = 0


class HistoricalAnalyzer:
    """Track quality trends and identify hotspots."""

    def __init__(self):
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._hotspots: dict[str, dict[str, Any]] = {}

    def record_review(
        self,
        tenant: str,
        repo_id: str,
        review: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> None:
        key = f"{tenant}:{repo_id}"
        if key not in self._history:
            self._history[key] = []

        entry = {
            "review_id": review.get("id", ""),
            "quality_scores": review.get("quality_scores", {}),
            "risk_score": review.get("risk_score", 0.0),
            "finding_counts": self._count_by_severity(findings),
            "total_findings": len(findings),
            "files_changed": list(set(f.get("file_path", "") for f in findings)),
            "gate_passed": review.get("gate_passed"),
        }
        self._history[key].append(entry)

        for f in findings:
            fp = f.get("file_path", "")
            if fp:
                if fp not in self._hotspots:
                    self._hotspots[fp] = {
                        "file_path": fp,
                        "change_count": 0,
                        "defect_count": 0,
                        "authors": [],
                    }
                self._hotspots[fp]["change_count"] += 1
                if f.get("severity") in ("critical", "high"):
                    self._hotspots[fp]["defect_count"] += 1

    def get_hotspots(
        self, tenant: str, repo_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        hotspots = []
        for fp, data in self._hotspots.items():
            defect_rate = data["defect_count"] / max(data["change_count"], 1)
            risk = min(1.0, defect_rate * 0.6 + min(data["change_count"] / 10, 0.4))
            hotspots.append({
                "file_path": fp,
                "change_count": data["change_count"],
                "defect_count": data["defect_count"],
                "risk_score": round(risk, 4),
                "authors": data["authors"],
            })
        hotspots.sort(key=lambda h: h["risk_score"], reverse=True)
        return hotspots[:limit]

    def get_trends(
        self, tenant: str, repo_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        key = f"{tenant}:{repo_id}"
        history = self._history.get(key, [])
        return history[-limit:]

    def compute_trend_direction(
        self, tenant: str, repo_id: str
    ) -> str:
        key = f"{tenant}:{repo_id}"
        history = self._history.get(key, [])
        if len(history) < 3:
            return "insufficient_data"

        recent = history[-3:]
        older = history[-6:-3] if len(history) >= 6 else history[:3]

        recent_findings = sum(h["total_findings"] for h in recent) / len(recent)
        older_findings = sum(h["total_findings"] for h in older) / len(older)

        recent_risk = sum(h["risk_score"] for h in recent) / len(recent)
        older_risk = sum(h["risk_score"] for h in older) / len(older)

        if recent_findings < older_findings and recent_risk < older_risk:
            return "improving"
        elif recent_findings > older_findings * 1.2 or recent_risk > older_risk * 1.2:
            return "declining"
        return "stable"

    def identify_recurring_defects(
        self, tenant: str, repo_id: str, min_occurrences: int = 3
    ) -> list[dict[str, Any]]:
        key = f"{tenant}:{repo_id}"
        history = self._history.get(key, [])

        file_defect_counts: dict[str, int] = {}
        for entry in history:
            for fp in entry.get("files_changed", []):
                finding_counts = entry.get("finding_counts", {})
                critical = finding_counts.get("critical", 0) + finding_counts.get("high", 0)
                if critical > 0:
                    file_defect_counts[fp] = file_defect_counts.get(fp, 0) + 1

        recurring = []
        for fp, count in file_defect_counts.items():
            if count >= min_occurrences:
                recurring.append({
                    "file_path": fp,
                    "defect_occurrences": count,
                    "risk": "high" if count >= 5 else "medium",
                })
        return sorted(recurring, key=lambda x: x["defect_occurrences"], reverse=True)

    def _count_by_severity(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1
        return counts
