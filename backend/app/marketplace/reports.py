"""User reports against marketplace packages (security, malware, policy, ...)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.marketplace.models import (
    MarketplacePackage,
    MarketplaceReport,
    ReportStatus,
)


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, package_slug: str, reporter_user_id, reporter_organization_id, report_type, description: str, release_id=None) -> MarketplaceReport:
        pkg = await self._pkg(package_slug)
        if not pkg:
            raise ValueError("package not found")
        report = MarketplaceReport(
            package_id=pkg.id,
            release_id=release_id,
            reporter_user_id=reporter_user_id,
            reporter_organization_id=reporter_organization_id,
            report_type=report_type,
            description=description,
            status=ReportStatus.OPEN,
            audit_trail=[{"action": "created", "at": datetime.now(timezone.utc).isoformat(), "by": str(reporter_user_id)}],
        )
        self.db.add(report)
        await self.db.flush()
        return report

    async def list(self, status=None, package_id=None, limit=50, offset=0):
        stmt = select(MarketplaceReport)
        if status:
            stmt = stmt.where(MarketplaceReport.status == status)
        if package_id:
            stmt = stmt.where(MarketplaceReport.package_id == package_id)
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (await self.db.execute(stmt.order_by(MarketplaceReport.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return rows, total

    async def resolve(self, report_id, status: ReportStatus, resolution: Optional[str] = None, assigned_to=None) -> Optional[MarketplaceReport]:
        rep = await self.db.get(MarketplaceReport, report_id)
        if not rep:
            return None
        rep.status = status
        rep.resolution = resolution
        rep.assigned_to = assigned_to
        rep.audit_trail = (rep.audit_trail or []) + [{
            "action": "resolved", "status": status.value, "at": datetime.now(timezone.utc).isoformat(),
            "by": str(assigned_to), "resolution": resolution,
        }]
        await self.db.flush()
        return rep

    async def act_on_report(self, report_id, action: str, admin_user_id=None) -> Optional[MarketplaceReport]:
        """Apply a security response action derived from a report.

        Supported actions: suspend, restrict, deprecate, retire. These change
        the package status (never silently modify customer environments)."""
        rep = await self.db.get(MarketplaceReport, report_id)
        if not rep:
            return None
        pkg = await self.db.get(MarketplacePackage, rep.package_id)
        if pkg and action in ("suspend", "restrict", "deprecate", "retire"):
            from app.marketplace.models import PackageStatus

            mapping = {"suspend": PackageStatus.SUSPENDED, "restrict": PackageStatus.RESTRICTED,
                       "deprecate": PackageStatus.DEPRECATED, "retire": PackageStatus.RETIRED}
            pkg.status = mapping[action]
            await self.db.flush()
        rep.status = ReportStatus.RESOLVED
        rep.audit_trail = (rep.audit_trail or []) + [{
            "action": "admin_action", "value": action, "at": datetime.now(timezone.utc).isoformat(), "by": str(admin_user_id),
        }]
        await self.db.flush()
        return rep

    async def _pkg(self, slug: str) -> Optional[MarketplacePackage]:
        res = await self.db.execute(
            select(MarketplacePackage)
            .options(selectinload(MarketplacePackage.publisher))
            .where(MarketplacePackage.slug == slug)
        )
        return res.scalar_one_or_none()
