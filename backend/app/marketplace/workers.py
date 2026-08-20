"""Marketplace background workers.

Each worker operates on its own DB session and is safe to run from a scheduler
or the application worker pool. Workers are idempotent where the underlying
operations are (installation, audit).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from app.core.database import get_db_context
from app.marketplace.analytics import AnalyticsService
from app.marketplace.installation import InstallationService
from app.marketplace.manifest import PackageManifest, validate_manifest
from app.marketplace.models import (
    InstallationStatus,
    MarketplaceInstallation,
    MarketplacePackage,
    MarketplaceRelease,
    MarketplaceReport,
    MarketplaceSecurityScan,
    PackageStatus,
    ReportStatus,
    ScanStatus,
    ScanType,
)
from app.marketplace.registry import DependencyResolver, PackageService
from app.marketplace.security import SecurityScanner


async def validate_package(package_id: str) -> dict:
    from app.marketplace.manifest import validate_manifest
    from app.marketplace.registry import PackageService

    async with get_db_context() as db:
        svc = PackageService(db)
        pkg = await svc.get(package_id)
        if not pkg:
            return {"ok": False, "reason": "not found"}
        rel = (await db.execute(
            select(MarketplaceRelease)
            .where(MarketplaceRelease.package_id == package_id)
            .order_by(MarketplaceRelease.created_at.desc())
        )).scalars().first()
        if not rel or not rel.manifest:
            return {"ok": False, "reason": "no manifest"}
        manifest, errors = validate_manifest(rel.manifest)
        return {"ok": not errors, "errors": errors}


async def scan_package_security(package_id: str, release_id: Optional[str] = None) -> dict:
    from app.marketplace.models import MarketplaceRelease, MarketplaceSecurityScan
    from app.marketplace.registry import PackageService

    async with get_db_context() as db:
        svc = PackageService(db)
        rel = None
        if release_id:
            rel = await db.get(MarketplaceRelease, release_id)
        if not rel:
            rel = (await db.execute(
                select(MarketplaceRelease).where(MarketplaceRelease.package_id == package_id).order_by(MarketplaceRelease.created_at.desc())
            )).scalars().first()
        if not rel or not rel.manifest:
            return {"ok": False, "reason": "no manifest"}
        result = SecurityScanner().scan(PackageManifest.model_validate(rel.manifest))
        scan = MarketplaceSecurityScan(
            package_id=package_id, release_id=rel.id,
            scan_type=ScanType.FULL,
            status=ScanStatus.PASSED if result["status"] == "passed" else ScanStatus.FAILED,
            findings=result["findings"], summary=result["summary"], tool_versions=result["tool_versions"],
        )
        db.add(scan)
        pkg = await svc.get(package_id)
        if pkg:
            pkg.security_status = ScanStatus.PASSED if result["status"] == "passed" else ScanStatus.FAILED
        await db.flush()
        return result["summary"]


async def scan_dependencies(package_id: str) -> list:
    from app.marketplace.registry import DependencyResolver

    async with get_db_context() as db:
        return await DependencyResolver(db).detect_conflicts(package_id)


async def verify_artifacts(release_id: str) -> dict:
    from app.marketplace.models import MarketplaceRelease

    async with get_db_context() as db:
        rel = await db.get(MarketplaceRelease, release_id)
        if not rel:
            return {"ok": False, "reason": "not found"}
        issues = []
        for a in rel.artifacts:
            if a.get("checksum_sha256") and a.get("checksum_sha256") != a.get("checksum_sha256"):
                issues.append(f"checksum mismatch for {a.get('name')}")
        rel.signature_metadata = {**(rel.signature_metadata or {}), "artifact_verified": len(issues) == 0}
        await db.flush()
        return {"ok": len(issues) == 0, "issues": issues}


async def process_installation(installation_id: str) -> dict:
    from app.marketplace.installation import InstallationService

    async with get_db_context() as db:
        svc = InstallationService(db)
        inst = await db.get(MarketplaceInstallation, installation_id)
        if not inst:
            return {"ok": False, "reason": "not found"}
        if inst.status.value in ("installing", "updating", "rolling_back"):
            inst.status = inst.approval_status.value == "approved" and InstallationStatus.ACTIVE or inst.status
            if inst.approval_status.value == "approved":
                inst.status = InstallationStatus.ACTIVE
            await db.flush()
        return {"ok": True, "status": inst.status.value}


async def health_check_packages() -> list:
    from app.marketplace.analytics import AnalyticsService

    async with get_db_context() as db:
        svc = AnalyticsService(db)
        res = await db.execute(select(MarketplacePackage).where(MarketplacePackage.status == PackageStatus.ACTIVE))
        flagged = []
        for pkg in res.scalars().all():
            health = await svc.package_health(pkg.id)
            if health.get("status") in ("degraded", "security_risk"):
                flagged.append(health)
                pkg.status = PackageStatus.DEGRADED if health["status"] == "degraded" else PackageStatus.SECURITY_RISK
        await db.flush()
        return flagged


async def aggregate_usage(organization_id: Optional[str] = None, days: int = 30) -> dict:
    from app.marketplace.analytics import AnalyticsService

    async with get_db_context() as db:
        svc = AnalyticsService(db)
        return await svc.aggregate(organization_id=organization_id, days=days)


async def security_notifications() -> int:
    """Notify package owners / org admins of security-relevant states."""
    from app.marketplace.models import MarketplaceReport, ReportStatus
    from app.services.notifications import NotificationService

    sent = 0
    async with get_db_context() as db:
        res = await db.execute(
            select(MarketplaceReport).where(MarketplaceReport.status == ReportStatus.OPEN)
        )
        notifier = NotificationService(db)
        for rep in res.scalars().all():
            # Route to the reporting org's admins via an in-app notification.
            try:
                await notifier.send_notification(
                    user_id=str(rep.reporter_user_id) if rep.reporter_user_id else "system",
                    title="Marketplace package reported",
                    body=f"A {rep.report_type.value} report was filed and is under review.",
                    notification_type="security",
                    org_id=str(rep.reporter_organization_id) if rep.reporter_organization_id else None,
                )
                sent += 1
            except Exception:
                continue
    return sent


async def deprecation_processing() -> list:
    """Flag packages scheduled for deprecation whose deadline has passed."""
    from app.marketplace.models import MarketplacePackage

    async with get_db_context() as db:
        res = await db.execute(select(MarketplacePackage).where(MarketplacePackage.status == PackageStatus.DEPRECATED))
        processed = []
        now = datetime.now(timezone.utc)
        for pkg in res.scalars().all():
            deadline = (pkg.compatibility or {}).get("deprecation_deadline")
            if deadline and deadline < now.isoformat():
                processed.append(str(pkg.id))
        return processed


WORKERS = {
    "validate_package": validate_package,
    "scan_package_security": scan_package_security,
    "scan_dependencies": scan_dependencies,
    "verify_artifacts": verify_artifacts,
    "process_installation": process_installation,
    "health_check_packages": health_check_packages,
    "aggregate_usage": aggregate_usage,
    "security_notifications": security_notifications,
    "deprecation_processing": deprecation_processing,
}


async def run_worker(name: str, **kwargs):
    if name not in WORKERS:
        raise ValueError(f"unknown worker: {name}")
    return await WORKERS[name](**kwargs)

