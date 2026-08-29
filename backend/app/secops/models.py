"""SecOps models — Volume 63 Commit 1 (additive-only, 7 tables).

Reuses Base/TimestampMixin, tenant-indexed, checkfirst.
Table `secops_findings` used instead of `security_findings` to avoid collision with
Volume 47 `security_findings` (same semantic, distinct table). All other names match spec.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin

# ── Enums / constants ───────────────────────────────────────────────────────
EVENT_CATEGORIES = {
    "AUTHENTICATION", "AUTHORIZATION", "NETWORK", "APPLICATION", "DATA",
    "AI", "AGENT", "CLOUD", "ENDPOINT", "SUPPLY_CHAIN", "CONFIGURATION", "IDENTITY",
}
SEVERITIES = {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
RULE_TYPES = {"threshold", "sequence", "frequency", "absence", "correlation", "anomaly", "policy_violation"}
ALERT_STATUSES = {"OPEN", "ACKNOWLEDGED", "INVESTIGATING", "CONTAINED", "RESOLVED", "FALSE_POSITIVE"}
FINDING_STATUSES = {"OPEN", "CONFIRMED", "MITIGATING", "RESOLVED", "ACCEPTED_RISK", "FALSE_POSITIVE"}
CASE_STATUSES = {"OPEN", "INVESTIGATING", "CONTAINED", "REMEDIATING", "RESOLVED", "CLOSED"}
INDICATOR_TYPES = {"IP", "domain", "URL", "hash", "package", "artifact", "account"}
INDICATOR_STATUSES = {"pending", "active", "expired", "removed"}

# ── 1. Detection rules (versioned) ───────────────────────────────────────────
class SecOpsDetectionRule(Base, TimestampMixin):
    __tablename__ = "security_detection_rules"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # EVENT_CATEGORIES
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # SEVERITIES
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # RULE_TYPES
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    threshold: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    time_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    owner: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    baseline_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_secops_rules_tenant_enabled", "tenant", "enabled"),
        Index("ix_secops_rules_tenant_category", "tenant", "category"),
    )


# ── 2. Security alerts ───────────────────────────────────────────────────────
class SecOpsAlert(Base, TimestampMixin):
    __tablename__ = "security_alerts"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    deduplication_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppression_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suppression_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_secops_alerts_tenant_status", "tenant", "status"),
        Index("ix_secops_alerts_rule", "rule_id"),
    )


# ── 3. Security findings (secops) — table secops_findings to avoid collision ──
class SecOpsFinding(Base, TimestampMixin):
    __tablename__ = "secops_findings"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    finding: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    policy: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    exposure: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    blast_radius: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_secops_findings_tenant_status", "tenant", "status"),
        Index("ix_secops_findings_resource", "resource_type", "resource_id"),
    )


# ── 4. Security cases ────────────────────────────────────────────────────────
class SecOpsCase(Base, TimestampMixin):
    __tablename__ = "security_cases"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    alerts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    owner: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    team: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    service_owner: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    __table_args__ = (
        Index("ix_secops_cases_tenant_status", "tenant", "status"),
    )


# ── 5. Case evidence ─────────────────────────────────────────────────────────
class SecOpsCaseEvidence(Base, TimestampMixin):
    __tablename__ = "security_case_evidence"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    event: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    integrity_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    collected_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    chain_of_custody: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (
        Index("ix_secops_evidence_case", "case_id"),
    )


# ── 6. Threat indicators ─────────────────────────────────────────────────────
class SecOpsIndicator(Base, TimestampMixin):
    __tablename__ = "security_indicators"

    tenant: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    indicator: Mapped[str] = mapped_column(String(512), nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    validated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feed_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_secops_indicators_type_value", "indicator_type", "indicator"),
        Index("ix_secops_indicators_status", "status"),
    )


# ── 7. Risk snapshots ────────────────────────────────────────────────────────
class SecOpsRiskSnapshot(Base, TimestampMixin):
    __tablename__ = "security_risk_snapshots"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    exposure: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    asset_criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    privilege: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    data_classification: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    method_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_secops_risk_resource", "resource_type", "resource_id"),
    )
