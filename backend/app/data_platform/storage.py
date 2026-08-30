"""Storage tiers HOT/WARM/COLD, retention, archival."""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataDataset


async def apply_retention(db: AsyncSession, tenant: str, dataset_id: str) -> dict:
    from app.data_platform.dataset import get_dataset
    ds = await get_dataset(db, tenant, dataset_id)
    if not ds or not ds.retention_days:
        return {"action": "none", "reason": "no retention policy"}
    age_days = (datetime.now(timezone.utc) - ds.created_at).days if ds.created_at else 0
    if age_days > ds.retention_days:
        # Check legal hold via governance
        try:
            from app.datagov.retention import retention_service
            # Check if legal hold exists
        except Exception:
            pass
        # For now, archive if HOT, delete if WARM
        if ds.storage_tier == "HOT":
            ds.storage_tier = "WARM"
            await db.flush()
            return {"action": "archive", "from": "HOT", "to": "WARM"}
        elif ds.storage_tier == "WARM":
            ds.status = "ARCHIVED"
            ds.storage_tier = "COLD"
            await db.flush()
            return {"action": "archive", "to": "COLD"}
        else:
            return {"action": "delete", "reason": "retention expired"}
    return {"action": "retain", "age_days": age_days}


async def archive_dataset(db: AsyncSession, tenant: str, dataset_id: str) -> dict:
    from app.data_platform.dataset import get_dataset
    ds = await get_dataset(db, tenant, dataset_id)
    if not ds:
        raise ValueError("dataset not found")
    ds.status = "ARCHIVED"
    ds.storage_tier = "COLD"
    await db.flush()
    return {"dataset_id": str(ds.id), "status": ds.status, "tier": ds.storage_tier}
