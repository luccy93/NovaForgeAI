"""Unified DevSecOps Security Platform -- Database Models (Volume 47)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class SecurityScan(Base, TimestampMixin):
    __tablename__ = "security_scans"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    repository: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scanner_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_security_scans_tenant", "tenant"),
        Index("ix_security_scans_target", "target_type", "target_id"),
        Index("ix_security_scans_tenant_status", "tenant", "status"),
    )


class SecurityFinding(Base, TimestampMixin):
    __tablename__ = "security_findings"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), ForeignKey("security_scans.id", ondelete="SET NULL"), nullable=True)
    project: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    repository: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    function: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    rule: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    remediation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scanner_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    dependency_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    dependency_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    cve_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    cwe_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    reachability: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    auto_remediable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_security_findings_tenant", "tenant"),
        Index("ix_security_findings_tenant_severity", "tenant", "severity"),
        Index("ix_security_findings_source_type", "source", "finding_type"),
        Index("ix_security_findings_repo_status", "repository", "status"),
        Index("ix_security_findings_fingerprint", "fingerprint"),
    )


class SecurityVulnerability(Base, TimestampMixin):
    __tablename__ = "security_vulnerabilities"

    cve_id: Mapped[str] = mapped_column(String(32), nullable=False)
    cwe_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cvss_vector: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    epss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    affected_package: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    affected_versions: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    fixed_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    ecosystem: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    references_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="nvd")
    exploitability: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_vulns_cve", "cve_id"),
    )


class SecuritySBOM(Base, TimestampMixin):
    __tablename__ = "security_sboms"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="cyclonedx")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    spec_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.5")
    component_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dependency_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    license_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    vulnerability_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    repository: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_security_sboms_tenant", "tenant"),
        Index("ix_security_sboms_target", "target_type", "target_id"),
    )


class SecuritySBOMComponent(Base, TimestampMixin):
    __tablename__ = "security_sbom_components"

    sbom_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("security_sboms.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    purl: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    ecosystem: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    license_id: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    license_name: Mapped[str] = mapped_column(String(256), nullable=False, default="unknown")
    hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    dependency_type: Mapped[str] = mapped_column(String(32), nullable=False, default="runtime")
    is_direct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="required")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_sbom_components_sbom", "sbom_id"),
    )


class SecurityAsset(Base, TimestampMixin):
    __tablename__ = "security_assets"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    repository: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    internet_exposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="development")
    owner: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    team: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_scan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    finding_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_assets_tenant", "tenant"),
        Index("ix_security_assets_tenant_type", "tenant", "asset_type"),
    )


class SecurityPolicy(Base, TimestampMixin):
    __tablename__ = "security_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False, default="gate")
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="repository")
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_policies_tenant", "tenant"),
        Index("ix_security_policies_tenant_type", "tenant", "policy_type"),
    )


class SecurityPolicyEvaluation(Base, TimestampMixin):
    __tablename__ = "security_policy_evaluations"

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("security_policies.id", ondelete="CASCADE"), nullable=False)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    matched_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_policy_evals_policy", "policy_id"),
    )


class SecurityRiskAcceptance(Base, TimestampMixin):
    __tablename__ = "security_risk_acceptances"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("security_findings.id", ondelete="CASCADE"), nullable=False)
    authorized_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_risk_acc_tenant", "tenant"),
        Index("ix_security_risk_acc_finding", "finding_id"),
    )


class SecurityFingerprint(Base, TimestampMixin):
    __tablename__ = "security_fingerprints"

    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("security_findings.id", ondelete="CASCADE"), nullable=False)
    rule: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    dependency: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    cve: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    artifact: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_security_fp_hash", "fingerprint_hash"),
        Index("ix_security_fp_finding", "finding_id"),
    )


class SecurityRemediation(Base, TimestampMixin):
    __tablename__ = "security_remediations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), ForeignKey("security_findings.id", ondelete="SET NULL"), nullable=True)
    remediation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    approach: Mapped[str] = mapped_column(Text, nullable=False, default="")
    patch_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pr_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    scan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), ForeignKey("security_scans.id", ondelete="SET NULL"), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_remediations_tenant", "tenant"),
        Index("ix_security_remediations_status", "tenant", "status"),
    )


class SecurityProvenance(Base, TimestampMixin):
    __tablename__ = "security_provenance"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    chain_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(256), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    build_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    artifact_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    builder: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    pipeline_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    deployment_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_prov_tenant", "tenant"),
        Index("ix_security_prov_chain", "chain_id"),
        Index("ix_security_prov_source", "source_type", "source_id"),
        Index("ix_security_prov_target", "target_type", "target_id"),
    )
