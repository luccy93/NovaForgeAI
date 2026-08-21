"""Incident Response Platform -- Configuration (Volume 49).

Configurable thresholds, dedup windows, escalation timeouts, SLO targets,
and AI investigation settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DedupConfig:
    window_seconds: int = 300
    fingerprint_fields: tuple[str, ...] = ("service", "environment", "rule_name", "key_labels")


@dataclass
class EscalationConfig:
    default_timeout_minutes: int = 30
    secondary_timeout_minutes: int = 60
    max_escalation_level: int = 3


@dataclass
class AnomalyConfig:
    latency_threshold_ms: float = 500.0
    error_rate_threshold: float = 0.05
    traffic_drop_percent: float = 30.0
    resource_usage_threshold: float = 0.85
    availability_threshold: float = 0.999
    detection_window_seconds: int = 300


@dataclass
class AIConfig:
    investigation_enabled: bool = True
    max_hypotheses: int = 5
    min_confidence_threshold: float = 0.3
    require_evidence: bool = True
    auto_triage: bool = True
    max_investigation_tokens: int = 5000


@dataclass
class RemediationConfig:
    require_approval_above: str = "moderate"
    dry_run_default: bool = True
    max_auto_executions_per_hour: int = 5
    rollback_on_failure: bool = True
    verification_required: bool = True


@dataclass
class PostmortemConfig:
    auto_generate: bool = True
    require_root_cause_evidence: bool = True
    follow_up_deadline_days: int = 30


@dataclass
class SLOConfig:
    default_availability_target: float = 0.999
    default_latency_target_ms: float = 200.0
    error_budget_alert_threshold: float = 0.1
    burn_rate_fast_threshold: float = 14.4
    burn_rate_medium_threshold: float = 6.0
    burn_rate_slow_threshold: float = 1.0


@dataclass
class IncidentConfig:
    dedup: DedupConfig = field(default_factory=DedupConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    anomaly: AnomalyConfig = field(default_factory=AnomalyConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    remediation: RemediationConfig = field(default_factory=RemediationConfig)
    postmortem: PostmortemConfig = field(default_factory=PostmortemConfig)
    slo: SLOConfig = field(default_factory=SLOConfig)

    @classmethod
    def default(cls) -> "IncidentConfig":
        return cls()

    @classmethod
    def strict(cls) -> "IncidentConfig":
        cfg = cls()
        cfg.dedup.window_seconds = 600
        cfg.escalation.default_timeout_minutes = 15
        cfg.anomaly.error_rate_threshold = 0.01
        cfg.ai.min_confidence_threshold = 0.5
        cfg.remediation.require_approval_above = "safe"
        return cfg
