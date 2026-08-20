"""AI Software Quality Engine -- Finding Model (Volume 48).

Validates findings, manages lifecycle states, computes dedup hashes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.quality.config import SEVERITY_WEIGHTS

VALID_CATEGORIES = {
    "correctness", "security", "reliability", "performance",
    "maintainability", "architecture", "testing", "api_compat",
    "database", "dependency", "observability", "documentation",
}

VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

VALID_SOURCES = {"sast", "sca", "ai_review", "code_smell", "test", "integration"}

VALID_STATUSES = {
    "open", "acknowledged", "in_progress", "fixed",
    "verified", "false_positive", "risk_accepted", "reopened",
}

STATUS_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "in_progress", "fixed", "false_positive", "risk_accepted"},
    "acknowledged": {"in_progress", "false_positive", "risk_accepted"},
    "in_progress": {"fixed", "open"},
    "fixed": {"verified", "reopened"},
    "verified": set(),
    "false_positive": {"open"},
    "risk_accepted": {"open"},
    "reopened": {"in_progress", "false_positive", "risk_accepted"},
}


@dataclass
class FindingData:
    """In-memory finding representation used by analyzers before DB persistence."""

    category: str
    severity: str
    confidence: float
    file_path: str
    line_start: int
    line_end: int
    symbol: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    rule_id: str = ""
    source: str = "ai_review"
    suggestion: str = ""
    diff_context: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {self.category}")
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {self.severity}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {self.source}")
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def finding_hash(self) -> str:
        raw = f"{self.category}:{self.rule_id}:{self.file_path}:{self.line_start}-{self.line_end}:{self.description}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "symbol": self.symbol,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "rule_id": self.rule_id,
            "source": self.source,
            "suggestion": self.suggestion,
            "diff_context": self.diff_context,
            "provenance": self.provenance,
            "finding_hash": self.finding_hash,
        }


def validate_finding(finding: FindingData) -> list[str]:
    """Validate a finding has required evidence and correct ranges."""
    errors: list[str] = []
    if not finding.description:
        errors.append("description is required")
    if not finding.evidence:
        errors.append("evidence is required for all findings")
    if finding.line_start < 0:
        errors.append("line_start must be >= 0")
    if finding.line_end > 0 and finding.line_end < finding.line_start:
        errors.append("line_end must be >= line_start")
    if not (0.0 <= finding.confidence <= 1.0):
        errors.append("confidence must be between 0.0 and 1.0")
    return errors


def transition_status(current: str, new_status: str) -> bool:
    """Check if a status transition is valid."""
    if current not in STATUS_TRANSITIONS:
        return False
    return new_status in STATUS_TRANSITIONS[current]


def severity_weight(severity: str) -> float:
    """Get numeric weight for a severity level."""
    return SEVERITY_WEIGHTS.get(severity, 1.0)
