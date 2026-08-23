"""Pydantic request/response schemas for the Marketplace API."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.marketplace.manifest import PackageManifest
from app.marketplace.models import (
    AccessScope,
    ApprovalStatus,
    BillingPeriod,
    DependencyType,
    EnvironmentType,
    InstallationStatus,
    LicensePolicyAction,
    ModerationStatus,
    PackageStatus,
    PackageType,
    PricingType,
    PublisherType,
    ReleaseChannel,
    ReportStatus,
    ReportType,
    ReviewStatus,
    RiskLevel,
    ScanStatus,
    ScanType,
    VerificationStatus,
)


# ─── Publishers ─────────────────────────────────────────────────────────


class PublisherCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    slug: str = Field(..., min_length=1, max_length=160, pattern="^[a-z0-9][a-z0-9-]{1,158}[a-z0-9]$")
    publisher_type: PublisherType = PublisherType.INDIVIDUAL
    contact_email: Optional[str] = Field(None, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    owner_organization_id: Optional[str] = None


class PublisherUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=160)
    contact_email: Optional[str] = Field(None, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)


class PublisherOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    publisher_type: PublisherType
    verification_status: VerificationStatus
    verification_methods: list
    domain: Optional[str]
    reputation_score: float
    security_incidents: int
    published_package_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PublisherVerifyRequest(BaseModel):
    method: str = Field(..., pattern="^(email|domain|organization)$")
    token: Optional[str] = None


# ─── Packages ──────────────────────────────────────────────────────────


class PackageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    slug: str = Field(..., min_length=1, max_length=160, pattern="^[a-z0-9][a-z0-9-]{1,158}[a-z0-9]$")
    package_type: PackageType
    publisher_id: uuid.UUID
    description: str = Field("", max_length=4000)
    license: str = "MIT"
    pricing_type: PricingType = PricingType.FREE
    price: float = 0.0
    currency: str = "USD"
    billing_period: BillingPeriod = BillingPeriod.ONE_TIME
    access_scope: AccessScope = AccessScope.PUBLIC
    organization_id: Optional[str] = None
    region: Optional[str] = Field(None, max_length=32)
    category: Optional[str] = Field(None, max_length=64)
    tags: list[str] = Field(default_factory=list)
    documentation: str = ""
    compatibility: dict = Field(default_factory=dict)
    icon_url: Optional[str] = None
    homepage: Optional[str] = None
    repository_url: Optional[str] = None
    release_channel: str = Field("stable", pattern="^(stable|beta|canary|edge)$")
    provenance: dict = Field(default_factory=dict)
    sbom: dict = Field(default_factory=dict)


class PackageUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=4000)
    license: Optional[str] = None
    pricing_type: Optional[PricingType] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    billing_period: Optional[BillingPeriod] = None
    access_scope: Optional[AccessScope] = None
    region: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    documentation: Optional[str] = None
    featured: Optional[bool] = None
    status: Optional[PackageStatus] = None


class PublisherSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    verification_status: VerificationStatus

    model_config = {"from_attributes": True}


class PackageOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    package_type: PackageType
    description: str
    publisher_id: uuid.UUID
    publisher: Optional[PublisherSummary] = None
    latest_version: Optional[str]
    status: PackageStatus
    governance_status: ApprovalStatus
    security_status: ScanStatus
    pricing_type: PricingType
    price: float
    currency: str
    billing_period: BillingPeriod
    license: str
    access_scope: AccessScope
    organization_id: Optional[uuid.UUID]
    region: Optional[str]
    featured: bool
    average_rating: float
    rating_count: int
    install_count: int
    view_count: int
    compatibility: Optional[dict]
    tags: list
    category: Optional[str]
    icon_url: Optional[str]
    homepage: Optional[str]
    repository_url: Optional[str]
    release_channel: Optional[str] = None
    provenance: Optional[dict] = None
    sbom: Optional[dict] = None
    moderation_status: Optional[str] = None
    health_score: Optional[float] = None
    health_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Releases ──────────────────────────────────────────────────────────


class ArtifactSpec(BaseModel):
    name: str
    kind: str = "file"
    url: str
    size: Optional[int] = None
    checksum_sha256: Optional[str] = None


class ReleaseCreate(BaseModel):
    version: str = Field(..., max_length=64)
    manifest: dict
    artifacts: list[ArtifactSpec] = Field(default_factory=list)
    changelog: str = ""
    build_metadata: dict = Field(default_factory=dict)
    yank: bool = False
    release_channel: str = Field("stable", pattern="^(stable|beta|canary|edge)$")
    provenance: dict = Field(default_factory=dict)
    sbom_ref: Optional[str] = None
    is_security_update: bool = False
    is_critical_update: bool = False
    is_breaking_update: bool = False


class ReleaseOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    version: str
    release_status: str
    checksum_sha256: Optional[str]
    signature: Optional[str]
    signature_metadata: Optional[dict]
    build_metadata: Optional[dict]
    manifest: Optional[dict]
    artifacts: list
    changelog: str
    is_yanked: bool
    published_at: Optional[datetime]
    release_channel: Optional[str] = None
    provenance: Optional[dict] = None
    sbom_ref: Optional[str] = None
    is_security_update: Optional[bool] = None
    is_critical_update: Optional[bool] = None
    is_breaking_update: Optional[bool] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Installations ─────────────────────────────────────────────────────


class InstallationCreate(BaseModel):
    package_slug: str
    environment: EnvironmentType = EnvironmentType.PRODUCTION
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    version: Optional[str] = None
    configuration: dict = Field(default_factory=dict)
    region: Optional[str] = None
    canary: bool = False
    dependency_lock: dict = Field(default_factory=dict)
    rollout_strategy: str = Field("manual", pattern="^(manual|all-at-once|staged|canary)$")


class InstallationUpdate(BaseModel):
    configuration: Optional[dict] = None
    status: Optional[InstallationStatus] = None
    environment: Optional[EnvironmentType] = None


class InstallationOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    package_slug: Optional[str] = None
    release_id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    installed_by: Optional[uuid.UUID]
    environment: EnvironmentType
    status: InstallationStatus
    approval_status: ApprovalStatus
    configuration: dict
    config_valid: bool
    entitlement_ref: Optional[str]
    security_scan_status: ScanStatus
    risk_level: RiskLevel
    risk_factors: list
    secrets_ref: list
    current_version: str
    previous_version: Optional[str]
    canary_stage: Optional[str]
    region: Optional[str]
    last_error: Optional[str]
    dependency_lock: Optional[dict] = None
    rollout_strategy: Optional[str] = None
    health_status: Optional[str] = None
    license_policy_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InstallationApproveRequest(BaseModel):
    approve: bool
    reason: Optional[str] = None


# ─── Reviews & reports ─────────────────────────────────────────────────


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str = Field("", max_length=160)
    body: str = Field("", max_length=4000)
    version: Optional[str] = None


class ReviewOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    rating: int
    title: str
    body: str
    is_version_specific: bool
    verified_install: bool
    status: ReviewStatus
    helpful_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportCreate(BaseModel):
    report_type: ReportType
    subject_type: Optional[str] = None
    subject_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None
    description: str = Field("", max_length=4000)
    release_id: Optional[uuid.UUID] = None


class ReportOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    report_type: ReportType
    description: str
    status: ReportStatus
    resolution: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Security scans ────────────────────────────────────────────────────


class SecurityScanOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    release_id: Optional[uuid.UUID]
    scan_type: ScanType
    status: ScanStatus
    findings: list
    summary: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Admin / moderation ───────────────────────────────────────────────


class ModerationRequest(BaseModel):
    action: str = Field(..., pattern="^(unlist|restrict|suspend|unsuspend|deprecate|retire|reinstate)$")
    reason: str = Field(..., min_length=1, max_length=500)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|restrict)$")
    reason: Optional[str] = None


class ConfigValidateRequest(BaseModel):
    package_type: Optional[str] = None
    configuration: list
    provided: dict = Field(default_factory=dict)


class ConfigValidateResponse(BaseModel):
    valid: bool
    errors: list
    secret_refs: list


# ─── Search & pagination ───────────────────────────────────────────────


class SearchFilters(BaseModel):
    query: Optional[str] = None
    package_type: Optional[PackageType] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    min_rating: Optional[float] = None
    pricing_type: Optional[PricingType] = None
    license: Optional[str] = None
    sort: str = Field("relevance", pattern="^(relevance|rating|installs|updated|created|name)$")
    include_private: bool = False


class SearchResultItem(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    package_type: PackageType
    description: str
    publisher_name: str
    publisher_verified: bool
    latest_version: Optional[str]
    average_rating: float
    rating_count: int
    install_count: int
    pricing_type: PricingType
    license: str
    security_status: ScanStatus
    governance_status: ApprovalStatus
    tags: list
    category: Optional[str]
    featured: bool


class PaginatedPackages(BaseModel):
    items: list[PackageOut]
    total: int
    limit: int
    offset: int

# ─── Volume 55 — Ecosystem extensions ─────────────────────────────────


class CategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    parent_id: Optional[uuid.UUID] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    slug: str = Field(..., pattern="^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=500)
    parent_id: Optional[uuid.UUID] = None
    sort_order: int = 0


class HealthOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    release_id: Optional[uuid.UUID] = None
    health_score: float
    health_status: str
    error_rate: float
    install_failures: int
    runtime_failures: int
    computed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmergencyBlockCreate(BaseModel):
    target_type: str = Field(..., pattern="^(package|version|publisher)$")
    target_id: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(..., min_length=1, max_length=500)
    scope: str = Field("global", pattern="^(global|organization)$")
    expires_at: Optional[datetime] = None


class EmergencyBlockOut(BaseModel):
    id: uuid.UUID
    target_type: str
    target_id: str
    reason: str
    scope: str
    expires_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LicensePolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    allowed_licenses: list[str] = Field(default_factory=list)
    denied_licenses: list[str] = Field(default_factory=list)
    review_required_licenses: list[str] = Field(default_factory=list)
    is_active: bool = True


class LicensePolicyOut(BaseModel):
    id: uuid.UUID
    organization_id: str
    name: str
    allowed_licenses: list
    denied_licenses: list
    review_required_licenses: list
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReputationOut(BaseModel):
    package_id: uuid.UUID
    reputation_score: float
    health_score: Optional[float] = None
    security_status: str
    install_count: int
    rating: float
    verified: bool

