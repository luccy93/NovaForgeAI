"""Marketplace orchestration facade used by the API layer.

Wraps the domain services, records immutable lifecycle audit events, and
publishes marketplace events to the EventBus (which fans out to webhooks).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.analytics import AnalyticsService
from app.marketplace.catalog import CatalogService
from app.marketplace.configuration import validate_configuration
from app.marketplace.installation import (
    CompatibilityError,
    EntitlementError,
    HostCapabilities,
    InstallationService,
)
from app.marketplace.models import (
    MarketplacePackage,
    MarketplacePackageEvent,
    MarketplacePublisher,
    ReportStatus,
)
from app.marketplace.publishers import PublisherService
from app.marketplace.registry import PackageService, ensure_permission_catalog
from app.marketplace.reports import ReportService
from app.marketplace.reviews import ReviewService
from app.marketplace.schemas import ConfigValidateRequest, ConfigValidateResponse
from app.marketplace.security import RiskCalculator, SecurityScanner


class MarketplaceService:
    def __init__(self, db: AsyncSession, subscription_manager=None):
        self.db = db
        self.publishers = PublisherService(db)
        self.packages = PackageService(db, SecurityScanner(), RiskCalculator())
        self.catalog = CatalogService(db)
        self.installations = InstallationService(db, RiskCalculator(), subscription_manager)
        self.reviews = ReviewService(db)
        self.reports = ReportService(db)
        self.analytics = AnalyticsService(db)

    # ── audit & events ──────────────────────────────────────────────

    async def audit(self, event_type: str, data: dict, organization_id=None, user_id=None, idempotency_key: Optional[str] = None) -> None:
        existing = None
        if idempotency_key:
            from sqlalchemy import select

            res = await self.db.execute(
                select(MarketplacePackageEvent).where(MarketplacePackageEvent.idempotency_key == idempotency_key)
            )
            existing = res.scalar_one_or_none()
        if existing:
            return  # idempotent
        self.db.add(MarketplacePackageEvent(
            package_id=data.get("package_id"),
            release_id=data.get("release_id"),
            organization_id=organization_id,
            user_id=user_id,
            event_type=event_type,
            event_data=data,
            idempotency_key=idempotency_key,
        ))
        await self.db.flush()

    # ── publishers ──────────────────────────────────────────────────

    async def ensure_catalog(self) -> int:
        return await ensure_permission_catalog(self.db)

    async def create_publisher(self, data, owner_user_id=None):
        pub = await self.publishers.create(data, owner_user_id)
        await self.audit("PublisherCreated", {"publisher_id": str(pub.id)}, user_id=owner_user_id)
        return pub

    async def verify_publisher(self, publisher_id, method, token=None):
        if method == "domain":
            token_sent, dns = await self.publishers.start_verification(publisher_id, method)
            ok = await self.publishers.verify_domain_dns(publisher_id) if token is None else await self.publishers.confirm_verification(publisher_id, method, token)
            return ok
        token_sent, _ = await self.publishers.start_verification(publisher_id, method)
        if token is None:
            return token_sent  # caller sends the token out-of-band
        return await self.publishers.confirm_verification(publisher_id, method, token)

    async def manual_verify_publisher(self, publisher_id, admin_user_id=None):
        return await self.publishers.manual_verify(publisher_id, admin_user_id)

    # ── packages & releases ─────────────────────────────────────────

    async def create_package(self, data, created_by=None):
        pkg = await self.packages.create_package(data, created_by)
        await self.audit("PackageCreated", {"package_id": str(pkg.id)}, user_id=created_by)
        return pkg

    async def publish_release(self, package_id, data, user_id=None):
        rel = await self.packages.publish_release(package_id, data, user_id)
        await self.audit("PackagePublished", {"package_id": str(package_id), "release_id": str(rel.id), "version": rel.version}, user_id=user_id)
        from app.marketplace.events import publish as publish_event

        await publish_event("PackagePublished", {"package_id": str(package_id), "version": rel.version}, user_id=user_id)
        return rel

    async def moderate_package(self, package_id, action: str, reason: str, admin_user_id=None):
        from app.marketplace.models import PackageStatus

        pkg = await self.packages.get(package_id)
        if not pkg:
            raise ValueError("package not found")
        mapping = {
            "unlist": PackageStatus.UNLISTED,
            "restrict": PackageStatus.RESTRICTED,
            "suspend": PackageStatus.SUSPENDED,
            "unsuspend": PackageStatus.ACTIVE,
            "deprecate": PackageStatus.DEPRECATED,
            "retire": PackageStatus.RETIRED,
            "reinstate": PackageStatus.ACTIVE,
        }
        if action not in mapping:
            raise ValueError(f"unknown moderation action: {action}")
        pkg.status = mapping[action]
        await self.db.flush()
        await self.audit("PackageModerated", {"package_id": str(package_id), "action": action, "reason": reason}, user_id=admin_user_id)
        from app.marketplace.events import publish as publish_event

        evt = {"PackageSuspended": "PackageSuspended", "PackageDeprecated": "PackageDeprecated", "PackageRetired": "PackageRetired"}.get(action)
        if evt:
            await publish_event(evt, {"package_id": str(package_id), "reason": reason}, user_id=admin_user_id)
        return pkg

    async def approve_package(self, package_id, decision: str, reason: Optional[str] = None, admin_user_id=None):
        from app.marketplace.models import ApprovalStatus

        pkg = await self.packages.get(package_id)
        if not pkg:
            raise ValueError("package not found")
        if decision == "approve":
            pkg.governance_status = ApprovalStatus.APPROVED
        elif decision == "reject":
            pkg.governance_status = ApprovalStatus.REJECTED
        elif decision == "restrict":
            pkg.governance_status = ApprovalStatus.RESTRICTED
        else:
            raise ValueError("decision must be approve/reject/restrict")
        await self.db.flush()
        await self.audit("PackageGovernanceDecision", {"package_id": str(package_id), "decision": decision, "reason": reason}, user_id=admin_user_id)
        return pkg

    # ── installations ───────────────────────────────────────────────

    async def install(self, organization_id, data, user_id=None, capabilities: Optional[HostCapabilities] = None):
        inst = await self.installations.install(organization_id, data, user_id, capabilities)
        await self.audit("PackageInstalled", {"package_id": str(inst.package_id), "installation_id": str(inst.id), "environment": inst.environment.value}, organization_id=organization_id, user_id=user_id)
        from app.marketplace.events import publish as publish_event

        await publish_event("PackageInstalled", {"package_id": str(inst.package_id), "organization_id": str(organization_id)}, organization_id=organization_id, user_id=user_id)
        return inst

    async def approve_installation(self, installation_id, approve, admin_user_id=None, reason=None):
        inst = await self.installations.approve(installation_id, approve, admin_user_id, reason)
        await self.audit("InstallationApproved", {"installation_id": str(inst.id), "approve": approve}, organization_id=str(inst.organization_id), user_id=admin_user_id)
        return inst

    async def configure_installation(self, installation_id, config):
        errors, secret_refs = [], []
        inst = await self.installations.configure(installation_id, config, errors, secret_refs)
        return inst

    async def update_installation(self, installation_id, version, user_id=None, capabilities: Optional[HostCapabilities] = None):
        return await self.installations.update(installation_id, version, user_id, capabilities)

    async def rollback_installation(self, installation_id, version, user_id=None, emergency=False):
        return await self.installations.rollback(installation_id, version, user_id, emergency)

    async def uninstall(self, installation_id, user_id=None):
        inst = await self.installations.uninstall(installation_id, user_id)
        await self.audit("PackageUninstalled", {"package_id": str(inst.package_id), "installation_id": str(inst.id)}, organization_id=str(inst.organization_id), user_id=user_id)
        from app.marketplace.events import publish as publish_event

        await publish_event("PackageUninstalled", {"package_id": str(inst.package_id), "organization_id": str(inst.organization_id)}, organization_id=str(inst.organization_id), user_id=user_id)
        return inst

    # ── reviews / reports ───────────────────────────────────────────

    async def add_review(self, package_slug, user_id, organization_id, data):
        return await self.reviews.create(package_slug, user_id, organization_id, data)

    async def moderate_review(self, review_id, status, moderator_user_id=None, reason=None):
        return await self.reviews.moderate(review_id, status, moderator_user_id, reason)

    async def add_report(self, package_slug, reporter_user_id, reporter_organization_id, report_type, description, release_id=None):
        rep = await self.reports.create(package_slug, reporter_user_id, reporter_organization_id, report_type, description, release_id)
        await self.audit("PackageReported", {"package_id": str(rep.package_id), "report_type": rep.report_type.value}, organization_id=reporter_organization_id, user_id=reporter_user_id)
        from app.marketplace.events import publish as publish_event

        await publish_event("PackageReported", {"package_id": str(rep.package_id), "report_type": rep.report_type.value}, organization_id=reporter_organization_id, user_id=reporter_user_id)
        return rep

    async def submit_report(self, organization_id, data, reporter_user_id=None):
        pkg = await self.db.get(MarketplacePackage, data.subject_id)
        if not pkg:
            raise ValueError("package not found")
        rep = await self.reports.create(pkg.slug, reporter_user_id, organization_id, data.report_type, data.description, release_id=None)
        await self.audit("PackageReported", {"package_id": str(pkg.id), "report_type": data.report_type.value}, organization_id=organization_id, user_id=reporter_user_id)
        from app.marketplace.events import publish as publish_event

        await publish_event("PackageReported", {"package_id": str(pkg.id), "report_type": data.report_type.value}, organization_id=organization_id, user_id=reporter_user_id)
        return rep

    async def list_reports(self, status=None, package_id=None):
        rows, _total = await self.reports.list(status=status, package_id=package_id)
        return rows

    async def resolve_report(self, report_id, moderator_user_id=None, resolution=None):
        rep = await self.reports.resolve(report_id, ReportStatus.RESOLVED, resolution, assigned_to=moderator_user_id)
        if rep:
            await self.audit("ReportResolved", {"report_id": str(report_id)}, organization_id=str(rep.reporter_organization_id), user_id=moderator_user_id)
        return rep

    async def act_on_report(self, report_id, action, moderator_user_id=None, notes=None):
        rep = await self.reports.act_on_report(report_id, action, moderator_user_id)
        if rep:
            await self.audit("ReportAction", {"report_id": str(report_id), "action": action}, organization_id=str(rep.reporter_organization_id), user_id=moderator_user_id)
        return rep

    # ── configuration ───────────────────────────────────────────────

    async def validate_config(self, request: ConfigValidateRequest) -> ConfigValidateResponse:
        from app.marketplace.manifest import ManifestConfigField

        fields = [ManifestConfigField(**f) for f in request.configuration]
        values = dict(request.provided)
        valid, errors, secret_refs = validate_configuration(fields, values)
        return ConfigValidateResponse(valid=valid, errors=errors, secret_refs=secret_refs)


__all__ = ["MarketplaceService", "CompatibilityError", "EntitlementError", "HostCapabilities"]
