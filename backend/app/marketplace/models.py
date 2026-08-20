"""NovaForge Marketplace — persistent domain models.

Implements the marketplace data layer: publishers, packages, immutable
releases, permissions catalog, dependency graph, installations, reviews,
reports, security scans, lifecycle events and usage metering.

All models follow the platform convention of ``Base`` + ``TimestampMixin``
with tenant/organization scoping where a package is organization-private.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


# ─── Enumerations ───────────────────────────────────────────────────────


class PackageType(str, enum.Enum):
    AGENT = "agent"
    TOOL = "tool"
    PLUGIN = "plugin"
    MCP_SERVER = "mcp_server"
    WORKFLOW = "workflow"
    PROMPT_PACK = "prompt_pack"
    RAG_CONNECTOR = "rag_connector"
    INTEGRATION = "integration"
    MODEL_ADAPTER = "model_adapter"
    IDE_EXTENSION = "ide_extension"


class PackageStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    UNLISTED = "unlisted"
    RESTRICTED = "restricted"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"
    SECURITY_RISK = "security_risk"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ReleaseStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    YANKED = "yanked"
    RETIRED = "retired"


class ApprovalStatus(str, enum.Enum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    RESTRICTED = "restricted"
    SUSPENDED = "suspended"


class PublisherType(str, enum.Enum):
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    VERIFIED_ORGANIZATION = "verified_organization"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    EMAIL_PENDING = "email_pending"
    EMAIL_VERIFIED = "email_verified"
    DOMAIN_PENDING = "domain_pending"
    DOMAIN_VERIFIED = "domain_verified"
    ORGANIZATION_VERIFIED = "organization_verified"
    MANUAL_VERIFIED = "manual_verified"


class PricingType(str, enum.Enum):
    FREE = "free"
    PAID = "paid"
    PRIVATE = "private"
    ORGANIZATION_ONLY = "organization_only"
    ENTERPRISE = "enterprise"


class BillingPeriod(str, enum.Enum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"
    ANNUAL = "annual"
    USAGE = "usage"


class AccessScope(str, enum.Enum):
    PUBLIC = "public"
    ORGANIZATION = "organization"
    WORKSPACE = "workspace"
    PROJECT = "project"
    PRIVATE = "private"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InstallationStatus(str, enum.Enum):
    INSTALLING = "installing"
    INSTALLED = "installed"
    CONFIGURING = "configuring"
    ACTIVE = "active"
    DISABLED = "disabled"
    FAILED = "failed"
    UPDATING = "updating"
    ROLLING_BACK = "rolling_back"
    UNINSTALLING = "uninstalling"
    UNINSTALLED = "uninstalled"


class EnvironmentType(str, enum.Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ReportType(str, enum.Enum):
    SECURITY = "security"
    SECURITY_ISSUE = "security_issue"
    MALWARE = "malware"
    ABUSE = "abuse"
    POLICY_VIOLATION = "policy_violation"
    MISLEADING = "misleading_functionality"
    COPYRIGHT = "copyright_license"
    BROKEN = "broken_package"


class ReportStatus(str, enum.Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewStatus(str, enum.Enum):
    PUBLISHED = "published"
    HIDDEN = "hidden"
    FLAGGED = "flagged"


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


class ScanSeverity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScanType(str, enum.Enum):
    MANIFEST = "manifest"
    PERMISSION = "permission"
    DEPENDENCY = "dependency"
    SECRET = "secret"
    STATIC = "static"
    LICENSE = "license"
    CONTAINER = "container"
    PROMPT_INJECTION = "prompt_injection"
    FULL = "full"


class DependencyType(str, enum.Enum):
    RUNTIME = "runtime"
    TOOL = "tool"
    MODEL = "model"
    INTEGRATION = "integration"
    PLUGIN = "plugin"
    WORKFLOW = "workflow"


# ─── Publishers ─────────────────────────────────────────────────────────


class MarketplacePublisher(Base, TimestampMixin):
    __tablename__ = "marketplace_publishers"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    publisher_type: Mapped[PublisherType] = mapped_column(
        Enum(PublisherType, name="marketplace_publisher_type", create_constraint=True),
        default=PublisherType.INDIVIDUAL,
        nullable=False,
    )
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    owner_organization_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="marketplace_verification_status", create_constraint=True),
        default=VerificationStatus.UNVERIFIED,
        nullable=False,
        index=True,
    )
    verification_methods: Mapped[list] = mapped_column(JSONB, default=list)
    verification_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    domain_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    domain_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reputation_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    security_incidents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_package_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    packages: Mapped[list["MarketplacePackage"]] = relationship(
        back_populates="publisher", cascade="all, delete-orphan"
    )


# ─── Packages (catalog) ─────────────────────────────────────────────────


class MarketplacePackage(Base, TimestampMixin):
    __tablename__ = "marketplace_packages"

    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    publisher_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_publishers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    package_type: Mapped[PackageType] = mapped_column(
        Enum(PackageType, name="marketplace_package_type", create_constraint=True), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    latest_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[PackageStatus] = mapped_column(
        Enum(PackageStatus, name="marketplace_package_status", create_constraint=True),
        default=PackageStatus.DRAFT,
        nullable=False,
        index=True,
    )
    governance_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="marketplace_governance_status", create_constraint=True),
        default=ApprovalStatus.APPROVED,
        nullable=False,
    )
    security_status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="marketplace_security_status", create_constraint=True),
        default=ScanStatus.PENDING,
        nullable=False,
    )
    pricing_type: Mapped[PricingType] = mapped_column(
        Enum(PricingType, name="marketplace_pricing_type", create_constraint=True),
        default=PricingType.FREE,
        nullable=False,
    )
    price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    billing_period: Mapped[BillingPeriod] = mapped_column(
        Enum(BillingPeriod, name="marketplace_billing_period", create_constraint=True),
        default=BillingPeriod.ONE_TIME,
        nullable=False,
    )
    license: Mapped[str] = mapped_column(String(64), default="MIT", nullable=False)
    documentation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    access_scope: Mapped[AccessScope] = mapped_column(
        Enum(AccessScope, name="marketplace_access_scope", create_constraint=True),
        default=AccessScope.PUBLIC,
        nullable=False,
        index=True,
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(64), index=True, nullable=True
    )
    region: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    average_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    install_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compatibility: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    category: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    homepage: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    repository_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    publisher: Mapped["MarketplacePublisher"] = relationship(back_populates="packages")
    releases: Mapped[list["MarketplaceRelease"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    installations: Mapped[list["MarketplaceInstallation"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["MarketplaceReview"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    reports: Mapped[list["MarketplaceReport"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    security_scans: Mapped[list["MarketplaceSecurityScan"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["MarketplaceDependency"]] = relationship(
        "MarketplaceDependency",
        foreign_keys="MarketplaceDependency.package_id",
        back_populates="package",
        cascade="all, delete-orphan",
    )
    dependents: Mapped[list["MarketplaceDependency"]] = relationship(
        "MarketplaceDependency",
        foreign_keys="MarketplaceDependency.depends_on_package_id",
        back_populates="depends_on",
        cascade="all, delete-orphan",
    )


# ─── Releases (immutable) ───────────────────────────────────────────────


class MarketplaceRelease(Base, TimestampMixin):
    __tablename__ = "marketplace_releases"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    release_status: Mapped[ReleaseStatus] = mapped_column(
        Enum(ReleaseStatus, name="marketplace_release_status", create_constraint=True),
        default=ReleaseStatus.DRAFT,
        nullable=False,
        index=True,
    )
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    build_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    manifest: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    artifacts: Mapped[list] = mapped_column(JSONB, default=list)
    changelog: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_yanked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    security_scan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    package: Mapped["MarketplacePackage"] = relationship(back_populates="releases")
    installations: Mapped[list["MarketplaceInstallation"]] = relationship(back_populates="release")
    security_scans: Mapped[list["MarketplaceSecurityScan"]] = relationship(back_populates="release")

    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_marketplace_release_pkg_ver"),
    )


# ─── Permission catalog ─────────────────────────────────────────────────


class MarketplacePermission(Base, TimestampMixin):
    __tablename__ = "marketplace_permissions"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="marketplace_permission_risk", create_constraint=True),
        default=RiskLevel.LOW,
        nullable=False,
    )
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    privileged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ─── Dependency graph ───────────────────────────────────────────────────


class MarketplaceDependency(Base, TimestampMixin):
    __tablename__ = "marketplace_dependencies"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_releases.id", ondelete="CASCADE"), nullable=True
    )
    depends_on_package_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=True
    )
    depends_on_slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    constraint: Mapped[str] = mapped_column(String(64), default="*", nullable=False)
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, name="marketplace_dependency_type", create_constraint=True),
        default=DependencyType.RUNTIME,
        nullable=False,
    )
    resolved_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    package: Mapped["MarketplacePackage"] = relationship(
        foreign_keys=[package_id], back_populates="dependencies"
    )
    depends_on: Mapped[Optional["MarketplacePackage"]] = relationship(
        foreign_keys=[depends_on_package_id], back_populates="dependents"
    )


# ─── Installations ──────────────────────────────────────────────────────


class MarketplaceInstallation(Base, TimestampMixin):
    __tablename__ = "marketplace_installations"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_releases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    installed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    environment: Mapped[EnvironmentType] = mapped_column(
        Enum(EnvironmentType, name="marketplace_environment", create_constraint=True),
        default=EnvironmentType.PRODUCTION,
        nullable=False,
    )
    status: Mapped[InstallationStatus] = mapped_column(
        Enum(InstallationStatus, name="marketplace_installation_status", create_constraint=True),
        default=InstallationStatus.INSTALLING,
        nullable=False,
        index=True,
    )
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    config_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    entitlement_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="marketplace_install_approval", create_constraint=True),
        default=ApprovalStatus.APPROVED,
        nullable=False,
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    governance_review_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    security_scan_status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="marketplace_install_scan", create_constraint=True),
        default=ScanStatus.PENDING,
        nullable=False,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="marketplace_install_risk", create_constraint=True),
        default=RiskLevel.LOW,
        nullable=False,
    )
    risk_factors: Mapped[list] = mapped_column(JSONB, default=list)
    secrets_ref: Mapped[list] = mapped_column(JSONB, default=list)
    current_version: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    canary_stage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    package: Mapped["MarketplacePackage"] = relationship(back_populates="installations")
    release: Mapped["MarketplaceRelease"] = relationship(back_populates="installations")

    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "organization_id",
            "workspace_id",
            "project_id",
            "environment",
            name="uq_marketplace_install_scope",
        ),
    )


# ─── Reviews ────────────────────────────────────────────────────────────


class MarketplaceReview(Base, TimestampMixin):
    __tablename__ = "marketplace_reviews"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_releases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_version_specific: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_install: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="marketplace_review_status", create_constraint=True),
        default=ReviewStatus.PUBLISHED,
        nullable=False,
    )
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    moderated_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    moderation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    package: Mapped["MarketplacePackage"] = relationship(back_populates="reviews")


# ─── Reports ────────────────────────────────────────────────────────────


class MarketplaceReport(Base, TimestampMixin):
    __tablename__ = "marketplace_reports"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_releases.id", ondelete="SET NULL"), nullable=True
    )
    reporter_user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    reporter_organization_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="marketplace_report_type", create_constraint=True), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="marketplace_report_status", create_constraint=True),
        default=ReportStatus.OPEN,
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audit_trail: Mapped[list] = mapped_column(JSONB, default=list)

    package: Mapped["MarketplacePackage"] = relationship(back_populates="reports")


# ─── Security scans ─────────────────────────────────────────────────────


class MarketplaceSecurityScan(Base, TimestampMixin):
    __tablename__ = "marketplace_security_scans"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_releases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scan_type: Mapped[ScanType] = mapped_column(
        Enum(ScanType, name="marketplace_scan_type", create_constraint=True),
        default=ScanType.FULL,
        nullable=False,
    )
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="marketplace_scan_status_enum", create_constraint=True),
        default=ScanStatus.PENDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    findings: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    tool_versions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    package: Mapped["MarketplacePackage"] = relationship(back_populates="security_scans")
    release: Mapped["MarketplaceRelease"] = relationship(back_populates="security_scans")


# ─── Lifecycle events (audit) ───────────────────────────────────────────


class MarketplacePackageEvent(Base, TimestampMixin):
    __tablename__ = "marketplace_package_events"

    package_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    release_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("marketplace_releases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)

    __table_args__ = (
        Index("ix_marketplace_events_type", "event_type"),
    )


# ─── Usage metering ─────────────────────────────────────────────────────


class MarketplacePackageUsage(Base, TimestampMixin):
    __tablename__ = "marketplace_package_usage"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("marketplace_releases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    installation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), index=True, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    metric: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    environment: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
