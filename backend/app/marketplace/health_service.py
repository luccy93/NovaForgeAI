"""Package health — separate from security status.

A package can be popular but insecure; health tracks operational signals
(install failures, runtime failures, crashes, latency, uninstall rate).
Never exposes private customer telemetry to publishers.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.models import MarketplaceHealth, MarketplacePackage, MarketplacePackageUsage


class HealthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_health(
        self,
        package_id: str,
        release_id: Optional[str] = None,
        metric: str = "install",
        value: float = 1.0,
        error: bool = False,
    ) -> MarketplaceHealth:
        # Upsert latest health row for package
        health = await self.db.scalar(select(MarketplaceHealth).where(MarketplaceHealth.package_id == package_id).order_by(MarketplaceHealth.computed_at.desc()).limit(1))  # type: ignore
        # Simpler: fetch or create
        existing = None
        res = await self.db.execute(select(MarketplaceHealth).where(MarketplaceHealth.package_id == package_id).order_by(MarketplaceHealth.computed_at.desc()).limit(1))
        existing = res.scalar_one_or_none()
        if existing is None:
            existing = MarketplaceHealth(
                package_id=package_id,
                release_id=release_id,
                health_score=1.0,
                health_status="healthy",
                error_rate=0.0,
                computed_at=datetime.now(timezone.utc),
            )
            self.db.add(existing)
            await self.db.flush()
        # Update counters based on metric
        if metric == "install_failure":
            existing.install_failures += 1
        elif metric == "runtime_failure":
            existing.runtime_failures += 1
        elif metric == "crash":
            existing.crashes += 1
        elif metric == "tool_error":
            existing.tool_errors += 1
        # Recompute error_rate & health_score
        total = (existing.install_failures + existing.runtime_failures + existing.crashes + existing.tool_errors + 10)
        errors = existing.install_failures + existing.runtime_failures + existing.crashes
        existing.error_rate = min(1.0, errors / max(1, total))
        # health_score 0..1, penalize error_rate and uninstall_rate
        existing.health_score = max(0.0, 1.0 - existing.error_rate * 0.8 - existing.uninstall_rate * 0.5)
        if existing.health_score < 0.4:
            existing.health_status = "degraded"
        elif existing.health_score < 0.7:
            existing.health_status = "warning"
        else:
            existing.health_status = "healthy"
        existing.computed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return existing

    async def get_health(self, package_id: str) -> Optional[MarketplaceHealth]:
        res = await self.db.execute(select(MarketplaceHealth).where(MarketplaceHealth.package_id == package_id).order_by(MarketplaceHealth.computed_at.desc()).limit(1))
        return res.scalar_one_or_none()

    async def aggregate_for_package(self, package_id: str) -> dict:
        health = await self.get_health(package_id)
        if not health:
            return {"health_score": 1.0, "health_status": "healthy", "error_rate": 0.0, "install_failures": 0, "runtime_failures": 0}
        return {
            "health_score": health.health_score,
            "health_status": health.health_status,
            "error_rate": health.error_rate,
            "install_failures": health.install_failures,
            "runtime_failures": health.runtime_failures,
            "crashes": health.crashes,
            "tool_errors": health.tool_errors,
            "uninstall_rate": health.uninstall_rate,
            "computed_at": health.computed_at.isoformat() if health.computed_at else None,
        }
