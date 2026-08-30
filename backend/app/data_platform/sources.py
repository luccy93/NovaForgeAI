"""Source registry — never raw credentials."""

import hashlib
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataSource

CONNECTORS = {"postgresql", "object_storage", "api", "git", "csv", "json", "parquet", "event_stream"}
STATUSES = {"ACTIVE", "INACTIVE", "DEPRECATED"}


async def register_source(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> DataSource:
    connector = (payload.get("connector") or "").lower()
    if connector not in CONNECTORS:
        raise ValueError(f"invalid connector {connector}")
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    # Credentials never raw: hash ref
    cred = payload.get("credentials") or payload.get("credentials_ref")
    cred_ref = None
    if cred:
        # Never store raw
        if len(cred) > 20 and "://" not in cred and cred.startswith("hash:"):
            cred_ref = cred
        else:
            # Hash it
            cred_ref = "hash:" + hashlib.sha256(str(cred).encode()).hexdigest()[:16]
    classification = (payload.get("classification") or "INTERNAL").upper()
    src = DataSource(
        tenant=tenant,
        name=name,
        connector=connector,
        credentials_ref=cred_ref,
        region=payload.get("region"),
        classification=classification,
        owner=payload.get("owner") or created_by,
        status=(payload.get("status") or "ACTIVE").upper(),
        config=payload.get("config") or {},
    )
    if src.status not in STATUSES:
        raise ValueError(f"invalid status {src.status}")
    db.add(src)
    await db.flush()
    return src


async def get_source(db: AsyncSession, tenant: str, source_id: str) -> DataSource | None:
    try:
        sid = uuid.UUID(source_id)
        q = select(DataSource).where(DataSource.id == sid, DataSource.tenant == tenant)
    except Exception:
        q = select(DataSource).where(DataSource.tenant == tenant, DataSource.name == source_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_sources(db: AsyncSession, tenant: str, connector: str | None = None, limit: int = 50) -> list[DataSource]:
    q = select(DataSource).where(DataSource.tenant == tenant)
    if connector:
        q = q.where(DataSource.connector == connector.lower())
    q = q.order_by(DataSource.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())
