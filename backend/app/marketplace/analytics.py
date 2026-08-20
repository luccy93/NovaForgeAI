"""Analytics, usage metering and package health."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import AnalyticsEvent, UsageRecord
from app.marketplace.models import (
    MarketplaceInstallation,
    MarketplacePackage,
    MarketplacePackageUsage,
    PackageStatus,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_event(self, organization_id, event_type: str, event_name: str, properties: Optional[dict] = None, user_id=None) -> None:
        self.db.add(AnalyticsEvent(
            organization_id=organization_id,
            user_id=user_id,
            event_type=event_type,
            event_name=event_name,
            properties=properties or {},
        ))
        await self.db.flush()

    async def record_usage(self, organization_id, metric: str, value: float, user_id=None) -> None:
        """Send a usage event to the shared metering sink (billing/FinOps)."""
        self.db.add(UsageRecord(
            organization_id=organization_id,
            metric=metric,
            value=value,
            recorded_at=datetime.now(timezone.utc),
        ))
        await self.db.flush()

    async def meter_package(self, package_id, release_id, organization_id, installation_id, metric: str, value: float, environment: str, user_id=None) -> None:
        self.db.add(MarketplacePackageUsage(
            package_id=package_id,
            release_id=release_id,
            organization_id=organization_id,
            installation_id=installation_id,
            user_id=user_id,
            metric=metric,
            value=value,
            environment=environment,
            recorded_at=datetime.now(timezone.utc),
        ))
        # Mirror to the shared usage sink for billing.
        await self.record_usage(organization_id, f"marketplace:{metric}", value, user_id)
        await self.db.flush()

    async def aggregate(self, package_id=None, organization_id=None, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(
            MarketplacePackageUsage.metric,
            func.sum(MarketplacePackageUsage.value),
            func.count(),
        ).where(MarketplacePackageUsage.recorded_at >= since)
        if package_id:
            stmt = stmt.where(MarketplacePackageUsage.package_id == package_id)
        if organization_id:
            stmt = stmt.where(MarketplacePackageUsage.organization_id == organization_id)
        rows = (await self.db.execute(stmt.group_by(MarketplacePackageUsage.metric))).all()
        return {r[0]: {"total": float(r[1] or 0), "count": int(r[2] or 0)} for r in rows}

    async def package_health(self, package_id) -> dict:
        """Compute a health assessment for a package."""
        pkg = await self.db.get(MarketplacePackage, package_id)
        if not pkg:
            return {}
        since = datetime.now(timezone.utc) - timedelta(days=30)
        failures = await self.db.scalar(
            select(func.count()).select_from(MarketplacePackageUsage).where(
                MarketplacePackageUsage.package_id == package_id,
                MarketplacePackageUsage.metric == "error",
                MarketplacePackageUsage.recorded_at >= since,
            )
        )
        installs = await self.db.scalar(
            select(func.count()).select_from(MarketplaceInstallation).where(MarketplaceInstallation.package_id == package_id)
        )
        error_rate = (float(failures or 0) / float(installs or 1)) if installs else 0.0
        status = "active"
        if pkg.status == PackageStatus.SUSPENDED:
            status = "suspended"
        elif pkg.status == PackageStatus.SECURITY_RISK:
            status = "security_risk"
        elif pkg.status == PackageStatus.DEPRECATED:
            status = "deprecated"
        elif pkg.security_status.value == "failed":
            status = "security_risk"
        elif error_rate > 0.25:
            status = "degraded"
        return {
            "package_id": str(package_id),
            "status": status,
            "error_rate": round(error_rate, 4),
            "active_installations": int(installs or 0),
            "errors_30d": int(failures or 0),
        }
