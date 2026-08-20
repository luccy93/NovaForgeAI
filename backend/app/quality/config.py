"""AI Software Quality Engine -- Configuration (Volume 48)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Review modes and their analyzer sets
REVIEW_MODES: dict[str, dict[str, Any]] = {
    "quick": {
        "analyzers": ["correctness", "code_smells"],
        "max_files": 10,
        "max_tokens": 5000,
        "max_runtime_s": 30,
        "max_cost_usd": 0.01,
        "use_llm": False,
    },
    "standard": {
        "analyzers": [
            "correctness",
            "performance",
            "reliability",
            "maintainability",
            "code_smells",
            "test_quality",
            "documentation",
        ],
        "max_files": 50,
        "max_tokens": 20000,
        "max_runtime_s": 120,
        "max_cost_usd": 0.05,
        "use_llm": True,
    },
    "deep": {
        "analyzers": [
            "correctness",
            "performance",
            "reliability",
            "architecture",
            "api_compat",
            "database",
            "dependency",
            "maintainability",
            "code_smells",
            "test_quality",
            "dead_code",
            "documentation",
            "ai_review",
        ],
        "max_files": 200,
        "max_tokens": 50000,
        "max_runtime_s": 300,
        "max_cost_usd": 0.20,
        "use_llm": True,
    },
    "security": {
        "analyzers": ["correctness", "dependency", "ai_review"],
        "max_files": 100,
        "max_tokens": 30000,
        "max_runtime_s": 180,
        "max_cost_usd": 0.10,
        "use_llm": True,
    },
    "performance": {
        "analyzers": ["performance", "reliability", "database", "ai_review"],
        "max_files": 100,
        "max_tokens": 30000,
        "max_runtime_s": 180,
        "max_cost_usd": 0.10,
        "use_llm": True,
    },
    "release": {
        "analyzers": [
            "correctness",
            "performance",
            "reliability",
            "architecture",
            "api_compat",
            "database",
            "dependency",
            "maintainability",
            "code_smells",
            "test_quality",
            "dead_code",
            "documentation",
            "ai_review",
        ],
        "max_files": 500,
        "max_tokens": 100000,
        "max_runtime_s": 600,
        "max_cost_usd": 0.50,
        "use_llm": True,
    },
}


# Severity weights for risk scoring
SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "high": 7.0,
    "medium": 4.0,
    "low": 2.0,
    "info": 1.0,
}


# Risk level thresholds (0.0-1.0 scale)
RISK_THRESHOLDS: dict[str, float] = {
    "low": 0.3,
    "medium": 0.6,
    "high": 0.85,
}


# Default quality gate rules
DEFAULT_GATE_RULES: list[dict[str, Any]] = [
    {
        "rule_type": "max_findings",
        "params": {"severity": "critical", "max_count": 0},
        "severity": "critical",
    },
    {
        "rule_type": "max_findings",
        "params": {"severity": "high", "max_count": 3},
        "severity": "high",
    },
    {
        "rule_type": "min_score",
        "params": {"dimension": "overall", "min_value": 0.6},
        "severity": "high",
    },
    {
        "rule_type": "no_breaking_changes",
        "params": {},
        "severity": "medium",
    },
]


# Category weights for quality score computation
CATEGORY_WEIGHTS: dict[str, float] = {
    "correctness": 0.25,
    "security": 0.20,
    "reliability": 0.15,
    "performance": 0.10,
    "architecture": 0.10,
    "maintainability": 0.10,
    "testing": 0.05,
    "documentation": 0.03,
    "api_compat": 0.02,
}


@dataclass
class ReviewConfig:
    """Configuration for a quality review run."""

    mode: str = "standard"
    analyzers: list[str] = field(default_factory=lambda: list(REVIEW_MODES["standard"]["analyzers"]))
    max_files: int = 50
    max_tokens: int = 20000
    max_runtime_s: int = 120
    max_cost_usd: float = 0.05
    use_llm: bool = True
    llm_model: str = ""
    fail_on_critical: bool = True
    fail_on_high: bool = False
    min_overall_score: float = 0.6

    @classmethod
    def from_mode(cls, mode: str) -> ReviewConfig:
        if mode not in REVIEW_MODES:
            mode = "standard"
        cfg = REVIEW_MODES[mode]
        return cls(
            mode=mode,
            analyzers=list(cfg["analyzers"]),
            max_files=cfg["max_files"],
            max_tokens=cfg["max_tokens"],
            max_runtime_s=cfg["max_runtime_s"],
            max_cost_usd=cfg["max_cost_usd"],
            use_llm=cfg["use_llm"],
        )
