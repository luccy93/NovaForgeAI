"""Marketplace REST API (Volume 44).

Replace the previous in-memory stub. All endpoints are tenant-scoped, use the
shared auth/RBAC dependencies, and delegate to :mod:`app.marketplace.service`.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user, require_permission
from app.core.authorization import Permission
from app.core.database import get_db
from app.marketplace.installation import CompatibilityError, EntitlementError, HostCapabilities
from app.marketplace.models import (
    ApprovalStatus,
    EnvironmentType,
    InstallationStatus,
    MarketplaceInstallation,
    MarketplaceRelease,
    PackageStatus,
    ReportStatus,
    ReportType,
    ReviewStatus,
    VerificationStatus,
)
from app.marketplace.schemas import (
    ConfigValidateRequest,
    ConfigValidateResponse,
    InstallationApproveRequest,
    InstallationCreate,
    InstallationOut,
    InstallationUpdate,
    PackageCreate,
    PackageOut,
    PackageUpdate,
    PublisherCreate,
    PublisherOut,
    PublisherVerifyRequest,
    ReleaseCreate,
    ReleaseOut,
    ReportCreate,
    ReportOut,
    ReviewCreate,
    ReviewOut,
    SearchFilters,
    SearchResultItem,
)
from app.marketplace.service import MarketplaceService

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


def _caps() -> HostCapabilities:
    return HostCapabilities(
        novaforge_version=os.environ.get("NOVAFORGE_VERSION", "1.0.0"),
        api_version="v1",
    )


def _org_id(user) -> uuid.UUID:
    oid = getattr(user, "organization_id", None)
    if not oid:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="No organization context")
    return oid


def _svc(db: AsyncSession = Depends(get_db)) -> MarketplaceService:
    return MarketplaceService(db)


def _not_found(detail="Not found"):
    raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=detail)


# ─── Categories (configurable taxonomy) ─────────────────────────────


CATEGORIES = [
    "Coding", "Code Review", "Security", "DevOps", "Testing", "Documentation",
    "RAG", "Data", "Productivity", "Agents", "Automation", "Integrations", "Developer Tools",
]


@router.get("/categories")
async def list_categories(svc: MarketplaceService = Depends(_svc)):
    # DB-backed configurable categories with seed fallback — not hard-coded hierarchy
    try:
        from app.marketplace.categories import CategoryService
        cat_svc = CategoryService(svc.db)
        await cat_svc.ensure_seeded()
        cats = await cat_svc.list(active_only=True)
        if cats:
            return [{"slug": c.slug, "name": c.name, "description": c.description} for c in cats]
    except Exception:
        pass
    return CATEGORIES


@router.post("/categories", status_code=201)
async def create_category(slug: str, name: str, description: str = "", user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    from app.marketplace.categories import CategoryService
    cat_svc = CategoryService(svc.db)
    try:
        cat = await cat_svc.create(slug=slug, name=name, description=description)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"slug": cat.slug, "name": cat.name, "description": cat.description}


# ─── Publishers ──────────────────────────────────────────────────────


@router.post("/publishers", response_model=PublisherOut, status_code=201)
async def create_publisher(data: PublisherCreate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    await svc.ensure_catalog()
    pub = await svc.create_publisher(data, str(user.id))
    return PublisherOut.model_validate(pub)


@router.get("/publishers", response_model=list[PublisherOut])
async def list_publishers(q: Optional[str] = None, verified_only: bool = False, limit: int = 50, offset: int = 0, svc: MarketplaceService = Depends(_svc)):
    rows, _ = await svc.publishers.list(q, verified_only, limit, offset)
    return [PublisherOut.model_validate(p) for p in rows]


@router.get("/publishers/{publisher_id}", response_model=PublisherOut)
async def get_publisher(publisher_id: str, svc: MarketplaceService = Depends(_svc)):
    pub = await svc.publishers.get(publisher_id)
    if not pub:
        _not_found("Publisher not found")
    return PublisherOut.model_validate(pub)


@router.post("/publishers/{publisher_id}/verify")
async def start_publisher_verification(publisher_id: str, body: PublisherVerifyRequest, svc: MarketplaceService = Depends(_svc)):
    # Returns the token to be delivered out-of-band (email/DNS) — never marks
    # the publisher verified by itself.
    result = await svc.verify_publisher(publisher_id, body.method, body.token)
    if isinstance(result, str):
        return {"status": "token_issued", "token": result, "method": body.method}
    return {"status": "verified" if result else "failed", "method": body.method}


@router.post("/publishers/{publisher_id}/verify/manual", response_model=PublisherOut)
async def manual_verify_publisher(publisher_id: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    pub = await svc.manual_verify_publisher(publisher_id, str(user.id))
    if not pub:
        _not_found("Publisher not found")
    return PublisherOut.model_validate(pub)


# ─── Packages & catalog ──────────────────────────────────────────────


@router.post("/packages", response_model=PackageOut, status_code=201)
async def create_package(data: PackageCreate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    await svc.ensure_catalog()
    pkg = await svc.create_package(data, str(user.id))
    return PackageOut.model_validate(pkg)


@router.get("/packages", response_model=list[PackageOut])
async def list_packages(
    package_type: Optional[str] = None,
    status: Optional[str] = None,
    publisher_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: MarketplaceService = Depends(_svc),
):
    from app.marketplace.models import PackageStatus as _PS, PackageType as _PT

    pt = _PT(package_type) if package_type else None
    st = _PS(status) if status else None
    rows, _ = await svc.packages.list(pt, st, publisher_id, limit, offset)
    return [PackageOut.model_validate(p) for p in rows]


@router.get("/search", response_model=dict)
async def search_packages(
    q: Optional[str] = None,
    package_type: Optional[str] = None,
    category: Optional[str] = None,
    publisher: Optional[str] = None,
    min_rating: Optional[float] = None,
    pricing_type: Optional[str] = None,
    license: Optional[str] = None,
    sort: str = "relevance",
    include_private: bool = False,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(_get_current_user),
    svc: MarketplaceService = Depends(_svc),
):
    from app.marketplace.models import PackageType as _PT, PricingType as _Pri

    filters = SearchFilters(
        query=q,
        package_type=_PT(package_type) if package_type else None,
        category=category,
        publisher=publisher,
        min_rating=min_rating,
        pricing_type=_Pri(pricing_type) if pricing_type else None,
        license=license,
        sort=sort,
        include_private=include_private,
    )
    items, total = await svc.catalog.search(filters, organization_id=str(_org_id(user)), limit=limit, offset=offset)
    return {
        "items": [SearchResultItem.model_validate(i).model_dump() for i in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/packages/{slug}", response_model=PackageOut)
async def get_package(slug: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.catalog.get_detail(slug, organization_id=str(_org_id(user)))
    if not pkg:
        _not_found("Package not found")
    await svc.catalog.record_view(pkg.id)
    return PackageOut.model_validate(pkg)


@router.patch("/packages/{slug}", response_model=PackageOut)
async def update_package(slug: str, data: PackageUpdate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    for field in ("description", "license", "pricing_type", "price", "currency", "billing_period", "access_scope", "region", "category", "tags", "documentation", "featured", "status"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(pkg, field, val)
    await svc.db.flush()
    return PackageOut.model_validate(pkg)


@router.post("/packages/{slug}/releases", response_model=ReleaseOut)
async def publish_release(slug: str, data: ReleaseCreate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    try:
        rel = await svc.publish_release(pkg.id, data, str(user.id))
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ReleaseOut.model_validate(rel)


@router.get("/packages/{slug}/releases", response_model=list[ReleaseOut])
async def list_releases(slug: str, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    from app.marketplace.models import MarketplaceRelease

    res = await svc.db.execute(
        select(MarketplaceRelease).where(MarketplaceRelease.package_id == pkg.id).order_by(MarketplaceRelease.created_at.desc())
    )
    return [ReleaseOut.model_validate(r) for r in res.scalars().all()]


@router.get("/packages/{slug}/releases/{version}", response_model=ReleaseOut)
async def get_release(slug: str, version: str, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    from app.marketplace.models import MarketplaceRelease

    res = await svc.db.execute(
        select(MarketplaceRelease).where(MarketplaceRelease.package_id == pkg.id, MarketplaceRelease.version == version)
    )
    rel = res.scalar_one_or_none()
    if not rel:
        _not_found("Release not found")
    return ReleaseOut.model_validate(rel)


@router.post("/packages/{slug}/security", response_model=dict)
async def scan_package(slug: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    from app.marketplace.workers import scan_package_security

    summary = await scan_package_security(str(pkg.id))
    return summary


# ─── Installations ───────────────────────────────────────────────────


@router.post("/install", response_model=InstallationOut)
async def install_package(data: InstallationCreate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    try:
        inst = await svc.install(str(_org_id(user)), data, str(user.id), _caps())
    except (CompatibilityError, EntitlementError, ValueError) as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    out = InstallationOut.model_validate(inst)
    out.package_slug = data.package_slug
    return out


@router.get("/installations", response_model=list[InstallationOut])
async def list_installations(environment: Optional[str] = None, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    rows = await svc.installations.list_for_org(str(_org_id(user)), environment, limit=200, offset=0)
    return [InstallationOut.model_validate(r) for r in rows]


@router.get("/installations/{installation_id}", response_model=InstallationOut)
async def get_installation(installation_id: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    inst = await svc.installations.installations.db.get(MarketplaceInstallation, installation_id) if False else await svc.db.get(MarketplaceInstallation, installation_id)
    if not inst:
        _not_found("Installation not found")
    return InstallationOut.model_validate(inst)


@router.put("/installations/{installation_id}", response_model=InstallationOut)
async def configure_installation(installation_id: str, data: InstallationUpdate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    inst = await svc.db.get(MarketplaceInstallation, installation_id)
    if not inst:
        _not_found("Installation not found")
    if data.configuration is not None:
        inst = await svc.configure_installation(installation_id, data.configuration)
    if data.status is not None:
        inst.status = data.status
        await svc.db.flush()
    return InstallationOut.model_validate(inst)


@router.post("/installations/{installation_id}/approve", response_model=InstallationOut)
async def approve_installation(installation_id: str, body: InstallationApproveRequest, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    inst = await svc.approve_installation(installation_id, body.approve, str(user.id), body.reason)
    return InstallationOut.model_validate(inst)


@router.post("/installations/{installation_id}/update", response_model=InstallationOut)
async def update_installation(installation_id: str, version: Optional[str] = None, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    try:
        inst = await svc.update_installation(installation_id, version, str(user.id), _caps())
    except (CompatibilityError, EntitlementError, ValueError) as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return InstallationOut.model_validate(inst)


@router.post("/installations/{installation_id}/rollback", response_model=InstallationOut)
async def rollback_installation(installation_id: str, version: str, emergency: bool = False, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    try:
        inst = await svc.rollback_installation(installation_id, version, str(user.id), emergency)
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return InstallationOut.model_validate(inst)


@router.post("/installations/{installation_id}/uninstall", response_model=InstallationOut)
async def uninstall_package(installation_id: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    inst = await svc.uninstall(installation_id, str(user.id))
    return InstallationOut.model_validate(inst)


@router.post("/installations/{installation_id}/canary", response_model=InstallationOut)
async def promote_canary(installation_id: str, stage: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    inst = await svc.installations.promote_canary(installation_id, stage)
    return InstallationOut.model_validate(inst)


# ─── Reviews ────────────────────────────────────────────────────────


@router.post("/reviews", response_model=ReviewOut, status_code=201)
async def create_review(data: ReviewCreate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    review = await svc.add_review(data.package_slug, str(user.id), str(_org_id(user)), data)
    return ReviewOut.model_validate(review)


@router.get("/packages/{slug}/reviews", response_model=dict)
async def list_reviews(slug: str, limit: int = 50, offset: int = 0, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    rows, total = await svc.reviews.list(pkg.id, limit, offset)
    return {"items": [ReviewOut.model_validate(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/reviews/{review_id}/moderate", response_model=ReviewOut)
async def moderate_review(review_id: str, status: str, reason: Optional[str] = None, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    rev = await svc.moderate_review(review_id, ReviewStatus(status), str(user.id), reason)
    if not rev:
        _not_found("Review not found")
    return ReviewOut.model_validate(rev)


# ─── Reports ────────────────────────────────────────────────────────


@router.post("/reports", response_model=ReportOut, status_code=201)
async def create_report(data: ReportCreate, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    rep = await svc.add_report(data.package_slug, str(user.id), str(_org_id(user)), ReportType(data.report_type), data.description, data.release_id)
    return ReportOut.model_validate(rep)


@router.get("/reports", response_model=dict)
async def list_reports(status: Optional[str] = None, limit: int = 50, offset: int = 0, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    rows, total = await svc.reports.list(ReportStatus(status) if status else None, None, limit, offset)
    return {"items": [ReportOut.model_validate(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/reports/{report_id}/resolve", response_model=ReportOut)
async def resolve_report(report_id: str, status: str, resolution: Optional[str] = None, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    rep = await svc.reports.resolve(report_id, ReportStatus(status), resolution, str(user.id))
    if not rep:
        _not_found("Report not found")
    return ReportOut.model_validate(rep)


@router.post("/reports/{report_id}/act", response_model=ReportOut)
async def act_on_report(report_id: str, action: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    rep = await svc.reports.act_on_report(report_id, action, str(user.id))
    if not rep:
        _not_found("Report not found")
    return ReportOut.model_validate(rep)


# ─── Configuration validation ───────────────────────────────────────


@router.post("/configuration/validate", response_model=ConfigValidateResponse)
async def validate_config(data: ConfigValidateRequest, svc: MarketplaceService = Depends(_svc)):
    return await svc.validate_config(data)


# ─── Analytics & health ─────────────────────────────────────────────


@router.get("/packages/{slug}/analytics")
async def package_analytics(slug: str, days: int = 30, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    return await svc.analytics.aggregate(package_id=pkg.id, days=days)


@router.get("/packages/{slug}/health")
async def package_health(slug: str, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    return await svc.analytics.package_health(pkg.id)


# ─── Ecosystem extensions (Volume 55) ─────────────────────────────────


@router.get("/packages/{slug}/versions", response_model=list[ReleaseOut])
async def list_package_versions(slug: str, svc: MarketplaceService = Depends(_svc)):
    # Alias to releases — published versions are immutable
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    from app.marketplace.models import MarketplaceRelease
    res = await svc.db.execute(select(MarketplaceRelease).where(MarketplaceRelease.package_id == pkg.id).order_by(MarketplaceRelease.created_at.desc()))
    return [ReleaseOut.model_validate(r) for r in res.scalars().all()]


@router.get("/permissions", response_model=list[dict])
async def list_permissions():
    from app.marketplace.manifest import PERMISSION_CATALOG
    return [{"key": k, **v, "risk_level": v["risk_level"].value if hasattr(v["risk_level"], "value") else str(v["risk_level"])} for k, v in PERMISSION_CATALOG.items()]


@router.get("/packages/{slug}/dependencies", response_model=list[dict])
async def list_dependencies(slug: str, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    from app.marketplace.models import MarketplaceDependency
    res = await svc.db.execute(select(MarketplaceDependency).where(MarketplaceDependency.package_id == pkg.id))
    rows = res.scalars().all()
    return [{"depends_on_slug": r.depends_on_slug, "constraint": r.constraint, "dependency_type": r.dependency_type.value} for r in rows]


@router.get("/packages/{slug}/reputation", response_model=dict)
async def get_reputation(slug: str, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    from app.marketplace.models import MarketplacePublisher
    from app.marketplace.reputation import compute_reputation
    from app.marketplace.health_service import HealthService
    pub = await svc.db.get(MarketplacePublisher, pkg.publisher_id) if pkg.publisher_id else None
    health_svc = HealthService(svc.db)
    health = await health_svc.get_health(str(pkg.id))
    hs = health.health_score if health else None
    rep = compute_reputation(pkg, pub, health_score=hs)
    return rep


@router.get("/packages/{slug}/security", response_model=dict)
async def get_security_status(slug: str, svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    spec_status = {"pending": "UNKNOWN", "in_progress": "SCANNING", "passed": "PASSED", "failed": "BLOCKED", "waived": "WARNING"}.get(pkg.security_status.value, pkg.security_status.value)
    return {"package_id": str(pkg.id), "security_status": pkg.security_status.value, "spec_status": spec_status, "governance_status": pkg.governance_status.value}


@router.post("/emergency-blocks", response_model=dict, status_code=201)
async def create_emergency_block(target_type: str, target_id: str, reason: str, scope: str = "global", expires_at: Optional[str] = None, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    from app.marketplace.emergency_block import EmergencyBlockService
    from datetime import datetime
    svc2 = EmergencyBlockService(svc.db)
    exp = datetime.fromisoformat(expires_at) if expires_at else None
    block = await svc2.create_block(target_type=target_type, target_id=target_id, reason=reason, scope=scope, expires_at=exp, created_by=str(user.id))
    return {"id": str(block.id), "target_type": block.target_type, "target_id": block.target_id, "reason": block.reason, "scope": block.scope}


@router.get("/emergency-blocks", response_model=list[dict])
async def list_emergency_blocks(user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    from app.marketplace.emergency_block import EmergencyBlockService
    svc2 = EmergencyBlockService(svc.db)
    blocks = await svc2.list_blocks(active_only=True)
    return [{"id": str(b.id), "target_type": b.target_type, "target_id": b.target_id, "reason": b.reason, "scope": b.scope} for b in blocks]


@router.delete("/emergency-blocks/{block_id}", response_model=dict)
async def delete_emergency_block(block_id: str, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    from app.marketplace.emergency_block import EmergencyBlockService
    svc2 = EmergencyBlockService(svc.db)
    block = await svc2.remove_block(block_id, removed_by=str(user.id))
    if not block:
        _not_found("Block not found")
    return {"deleted": block_id}


@router.post("/license-policies", response_model=dict, status_code=201)
async def create_license_policy(name: str, allowed_licenses: Optional[str] = None, denied_licenses: Optional[str] = None, review_required_licenses: Optional[str] = None, user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    from app.marketplace.license_policy import LicensePolicyService
    import json as _json
    svc2 = LicensePolicyService(svc.db)
    def parse(s):
        if not s:
            return []
        try:
            return _json.loads(s) if s.startswith("[") else [x.strip() for x in s.split(",")]
        except Exception:
            return [s]
    pol = await svc2.create_policy(str(_org_id(user)), name, allowed_licenses=parse(allowed_licenses), denied_licenses=parse(denied_licenses), review_required_licenses=parse(review_required_licenses))
    return {"id": str(pol.id), "name": pol.name}


@router.get("/license-policies", response_model=list[dict])
async def list_license_policies(user=Depends(_get_current_user), svc: MarketplaceService = Depends(_svc)):
    from app.marketplace.license_policy import LicensePolicyService
    svc2 = LicensePolicyService(svc.db)
    rows = await svc2.list_policies(str(_org_id(user)))
    return [{"id": str(r.id), "name": r.name, "allowed": r.allowed_licenses, "denied": r.denied_licenses} for r in rows]


# ─── Admin ──────────────────────────────────────────────────────────


@router.post("/admin/packages/{slug}/moderate", response_model=PackageOut)
async def admin_moderate(slug: str, action: str, reason: str, user=Depends(require_permission(Permission.admin_all)), svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    pkg = await svc.moderate_package(pkg.id, action, reason, str(user.id))
    return PackageOut.model_validate(pkg)


@router.post("/admin/packages/{slug}/approve", response_model=PackageOut)
async def admin_approve(slug: str, decision: str, reason: Optional[str] = None, user=Depends(require_permission(Permission.admin_all)), svc: MarketplaceService = Depends(_svc)):
    pkg = await svc.packages.get_by_slug(slug)
    if not pkg:
        _not_found("Package not found")
    pkg = await svc.approve_package(pkg.id, decision, reason, str(user.id))
    return PackageOut.model_validate(pkg)

