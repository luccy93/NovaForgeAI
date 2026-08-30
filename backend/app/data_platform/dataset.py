"""Dataset service — lifecycle, ownership, classification, region."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataDataset, DataDatasetVersion

DATASET_STATUSES = {"DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED", "BLOCKED"}
CLASSIFICATIONS = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}

def _to_uuid(v):
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


async def create_dataset(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> DataDataset:
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    # Check unique per tenant
    q = select(DataDataset).where(DataDataset.tenant == tenant, DataDataset.name == name)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("dataset name already exists for tenant")
    classification = (payload.get("classification") or "INTERNAL").upper()
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"invalid classification {classification}")
    status = (payload.get("status") or "DRAFT").upper()
    if status not in DATASET_STATUSES:
        raise ValueError(f"invalid status {status}")
    region = payload.get("region")
    # Region residency for RESTRICTED is enforced at processing time (pipeline/stream), not at catalog creation
    # Keep dataset creation permissive to allow cataloging; governance will flag if needed
    ds = DataDataset(
        tenant=tenant,
        workspace=payload.get("workspace"),
        project=payload.get("project"),
        name=name,
        description=payload.get("description", ""),
        owner=payload.get("owner") or created_by,
        team=payload.get("team"),
        classification=classification,
        schema_version=payload.get("schema_version", "1.0"),
        storage_location=payload.get("storage_location") or f"s3://{tenant}/{name}",
        storage_tier=payload.get("storage_tier", "HOT"),
        region=region,
        status=status,
        retention_days=payload.get("retention_days"),
    )
    # Ownership governance finding if missing for ACTIVE
    if status == "ACTIVE" and not ds.owner:
        try:
            from app.data_platform.governance import create_governance_finding
            await create_governance_finding(db, tenant, f"dataset {name} missing owner", "ownership")
        except Exception:
            pass
    db.add(ds)
    await db.flush()
    # Create initial version
    ver = DataDatasetVersion(
        dataset_id=ds.id,
        tenant=tenant,
        version="1.0",
        schema_version=ds.schema_version,
        storage_path=ds.storage_location,
        created_by=created_by,
    )
    db.add(ver)
    await db.flush()
    return ds


async def get_dataset(db: AsyncSession, tenant: str, dataset_id: str) -> DataDataset | None:
    try:
        did = _to_uuid(dataset_id)
        q = select(DataDataset).where(DataDataset.id == did, DataDataset.tenant == tenant)
    except Exception:
        q = select(DataDataset).where(DataDataset.tenant == tenant, DataDataset.name == dataset_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_datasets(db: AsyncSession, tenant: str, status: str | None = None, classification: str | None = None, owner: str | None = None, limit: int = 50) -> list[DataDataset]:
    q = select(DataDataset).where(DataDataset.tenant == tenant)
    if status:
        q = q.where(DataDataset.status == status.upper())
    if classification:
        q = q.where(DataDataset.classification == classification.upper())
    if owner:
        q = q.where(DataDataset.owner == owner)
    q = q.order_by(DataDataset.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def update_dataset_status(db: AsyncSession, tenant: str, dataset_id: str, new_status: str) -> DataDataset:
    ds = await get_dataset(db, tenant, dataset_id)
    if not ds:
        raise ValueError("dataset not found")
    ns = new_status.upper()
    if ns not in DATASET_STATUSES:
        raise ValueError(f"invalid status {ns}")
    # BLOCKED is governance action, not user transition
    if ns == "BLOCKED" and ds.status != "ACTIVE":
        raise ValueError("only ACTIVE can be BLOCKED")
    ds.status = ns
    await db.flush()
    return ds


async def create_version(db: AsyncSession, tenant: str, dataset_id: str, payload: dict) -> DataDatasetVersion:
    ds = await get_dataset(db, tenant, dataset_id)
    if not ds:
        raise ValueError("dataset not found")
    # Archived datasets can still have versions for recovery — immutability is per version, not dataset status
    version = payload.get("version")
    if not version:
        raise ValueError("version required")
    # Check immutable: version must not exist
    q = select(DataDatasetVersion).where(DataDatasetVersion.dataset_id == ds.id, DataDatasetVersion.version == version)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("version already exists — immutable")
    ver = DataDatasetVersion(
        dataset_id=ds.id,
        tenant=tenant,
        version=version,
        schema_version=payload.get("schema_version", ds.schema_version),
        pipeline_version=payload.get("pipeline_version"),
        storage_path=payload.get("storage_path"),
        row_count=payload.get("row_count"),
        checksum=payload.get("checksum"),
        created_by=payload.get("created_by"),
    )
    ds.schema_version = ver.schema_version
    db.add(ver)
    await db.flush()
    return ver
