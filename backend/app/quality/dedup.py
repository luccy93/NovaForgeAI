"""AI Software Quality Engine -- Finding Deduplication (Volume 48).

Merges duplicate findings across analyzers while preserving
all source scanners and evidence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DedupGroup:
    group_hash: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    merged_severity: str = "info"
    merged_confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    description: str = ""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0


SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


class FindingDeduplicator:
    """Deduplicate findings by content similarity and merge evidence."""

    def compute_hash(self, finding: dict[str, Any]) -> str:
        parts = [
            finding.get("category", ""),
            finding.get("rule_id", ""),
            finding.get("file_path", ""),
            str(finding.get("line_start", 0)),
            str(finding.get("line_end", 0)),
            finding.get("description", "")[:200],
        ]
        raw = ":".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def deduplicate(self, findings: list[dict[str, Any]]) -> list[DedupGroup]:
        hash_map: dict[str, DedupGroup] = {}

        for f in findings:
            h = self.compute_hash(f)
            if h in hash_map:
                group = hash_map[h]
                group.findings.append(f)
                source = f.get("source", "unknown")
                if source not in group.sources:
                    group.sources.append(source)
                self._update_merged_severity(group, f)
                self._merge_evidence(group, f)
            else:
                group = DedupGroup(
                    group_hash=h,
                    findings=[f],
                    merged_severity=f.get("severity", "info"),
                    merged_confidence=f.get("confidence", 0.5),
                    sources=[f.get("source", "unknown")],
                    description=f.get("description", ""),
                    file_path=f.get("file_path", ""),
                    line_start=f.get("line_start", 0),
                    line_end=f.get("line_end", 0),
                )
                hash_map[h] = group

        return list(hash_map.values())

    def _update_merged_severity(self, group: DedupGroup, finding: dict[str, Any]):
        current_rank = SEVERITY_RANK.get(group.merged_severity, 1)
        new_rank = SEVERITY_RANK.get(finding.get("severity", "info"), 1)
        if new_rank > current_rank:
            group.merged_severity = finding["severity"]
        group.merged_confidence = max(group.merged_confidence, finding.get("confidence", 0.5))

    def _merge_evidence(self, group: DedupGroup, finding: dict[str, Any]):
        existing_evidence = group.findings[0].get("evidence", {})
        new_evidence = finding.get("evidence", {})
        for key, value in new_evidence.items():
            if key not in existing_evidence:
                existing_evidence[key] = value

    def to_dicts(self, groups: list[DedupGroup]) -> list[dict[str, Any]]:
        result = []
        for g in groups:
            representative = g.findings[0].copy()
            representative["finding_hash"] = g.group_hash
            representative["severity"] = g.merged_severity
            representative["confidence"] = g.merged_confidence
            representative["source"] = "+".join(g.sources)
            representative["duplicate_count"] = len(g.findings)
            result.append(representative)
        return result
