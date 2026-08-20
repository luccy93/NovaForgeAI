"""AI Software Quality Engine -- Finding Correlation (Volume 48).

Links related findings across analyzers and detects cascading issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CorrelatedGroup:
    group_id: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    combined_severity: str = "info"
    combined_confidence: float = 0.0
    description: str = ""
    root_cause: str = ""
    cascading_risk: float = 0.0


SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}

CORRELATION_RULES: list[dict[str, Any]] = [
    {
        "id": "security_correctness",
        "categories": {"security", "correctness"},
        "description": "Security issue combined with correctness problem",
        "escalation": 0.2,
    },
    {
        "id": "performance_reliability",
        "categories": {"performance", "reliability"},
        "description": "Performance concern combined with reliability issue",
        "escalation": 0.15,
    },
    {
        "id": "architecture_maintainability",
        "categories": {"architecture", "maintainability"},
        "description": "Architecture violation combined with maintainability issue",
        "escalation": 0.1,
    },
    {
        "id": "testing_coverage",
        "categories": {"testing", "correctness"},
        "description": "Test gap combined with correctness concern",
        "escalation": 0.15,
    },
    {
        "id": "dependency_security",
        "categories": {"dependency", "security"},
        "description": "Dependency issue combined with security concern",
        "escalation": 0.2,
    },
    {
        "id": "database_migration",
        "categories": {"database", "api_compat"},
        "description": "Database change combined with API compatibility concern",
        "escalation": 0.25,
    },
]


class FindingCorrelator:
    """Correlate findings across analyzers and detect cascading issues."""

    def correlate(
        self, findings: list[dict[str, Any]]
    ) -> list[CorrelatedGroup]:
        if not findings:
            return []

        file_groups: dict[str, list[dict[str, Any]]] = {}
        for f in findings:
            fp = f.get("file_path", "")
            if fp:
                file_groups.setdefault(fp, []).append(f)

        correlated: list[CorrelatedGroup] = []
        group_id = 0

        for file_path, file_findings in file_groups.items():
            if len(file_findings) < 2:
                continue

            categories = set(f.get("category", "") for f in file_findings)
            for rule in CORRELATION_RULES:
                if rule["categories"].issubset(categories):
                    matching = [
                        f for f in file_findings
                        if f.get("category", "") in rule["categories"]
                    ]
                    if len(matching) >= 2:
                        group_id += 1
                        combined = self._combine_severity(matching)
                        combined_conf = max(f.get("confidence", 0.5) for f in matching)
                        escalated = min(
                            1.0, combined_conf + rule["escalation"]
                        )
                        correlated.append(
                            CorrelatedGroup(
                                group_id=f"corr_{group_id}",
                                findings=matching,
                                categories=list(rule["categories"]),
                                combined_severity=combined,
                                combined_confidence=round(escalated, 4),
                                description=rule["description"],
                                root_cause=rule["id"],
                                cascading_risk=round(rule["escalation"], 4),
                            )
                        )

        multi_source = self._find_multi_source_correlations(findings)
        correlated.extend(multi_source)

        return correlated

    def _combine_severity(self, findings: list[dict[str, Any]]) -> str:
        max_rank = 0
        result = "info"
        for f in findings:
            rank = SEVERITY_RANK.get(f.get("severity", "info"), 1)
            if rank > max_rank:
                max_rank = rank
                result = f.get("severity", "info")
        return result

    def _find_multi_source_correlations(
        self, findings: list[dict[str, Any]]
    ) -> list[CorrelatedGroup]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for f in findings:
            fp = f.get("file_path", "")
            ln = f.get("line_start", 0)
            key = f"{fp}:{ln // 5}" if ln > 0 else fp
            groups.setdefault(key, []).append(f)

        correlated: list[CorrelatedGroup] = []
        gid = 1000
        for key, group_findings in groups.items():
            sources = set(f.get("source", "") for f in group_findings)
            if len(sources) >= 2 and len(group_findings) >= 2:
                gid += 1
                categories = list(set(f.get("category", "") for f in group_findings))
                combined = self._combine_severity(group_findings)
                correlated.append(
                    CorrelatedGroup(
                        group_id=f"multi_{gid}",
                        findings=group_findings,
                        categories=categories,
                        combined_severity=combined,
                        combined_confidence=max(
                            f.get("confidence", 0.5) for f in group_findings
                        ),
                        description=f"Multiple analyzers found issues at same location ({', '.join(sources)})",
                        root_cause="multi_source",
                        cascading_risk=0.3,
                    )
                )
        return correlated

    def escalate_severity(
        self, severity: str, escalation: float
    ) -> str:
        rank = SEVERITY_RANK.get(severity, 1)
        new_rank = min(5, rank + int(escalation * 5))
        for name, r in SEVERITY_RANK.items():
            if r == new_rank:
                return name
        return severity
