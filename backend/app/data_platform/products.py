"""Data products — reusable governed datasets."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models_lakehouse import DataProduct, DataDomain
import uuid

PRODUCT_STATUSES = {"DRAFT", "PUBLISHED", "DEPRECATED", "RETIRED"}


async def create_product(db: AsyncSession, tenant: str, payload: dict) -> DataProduct:
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    q = select(DataProduct).where(DataProduct.tenant == tenant, DataProduct.name == name)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("product name already exists")
    owner = payload.get("owner")
    if not owner:
        raise ValueError("owner required")
    # Quality/SLO checks before publication
    if (payload.get("status") or "DRAFT").upper() == "PUBLISHED":
        # Require quality checks
        contract = payload.get("contract", {})
        if not contract.get("quality") or not contract.get("slo"):
            raise ValueError("published product requires contract.quality and contract.slo")
    prod = DataProduct(
        tenant=tenant,
        name=name,
        description=payload.get("description", ""),
        owner=owner,
        contract=payload.get("contract", {}),
        classification=(payload.get("classification") or "INTERNAL").upper(),
        status=(payload.get("status") or "DRAFT").upper(),
        domain=payload.get("domain"),
        slo=payload.get("slo", {}),
    )
    if prod.status not in PRODUCT_STATUSES:
        raise ValueError(f"invalid status {prod.status}")
    db.add(prod)
    await db.flush()
    if prod.status == "PUBLISHED":
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.DataProductPublished, {"product_id": str(prod.id)}, source="data_platform", organization_id=tenant))
        except Exception:
            pass
    return prod


async def get_product(db: AsyncSession, tenant: str, product_id: str) -> DataProduct | None:
    try:
        pid = uuid.UUID(product_id)
        q = select(DataProduct).where(DataProduct.id == pid, DataProduct.tenant == tenant)
    except Exception:
        q = select(DataProduct).where(DataProduct.tenant == tenant, DataProduct.name == product_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_products(db: AsyncSession, tenant: str, status: str | None = None, limit: int = 50) -> list[DataProduct]:
    q = select(DataProduct).where(DataProduct.tenant == tenant)
    if status:
        q = q.where(DataProduct.status == status.upper())
    q = q.order_by(DataProduct.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def create_domain(db: AsyncSession, tenant: str, name: str, owner: str, description: str | None = None) -> DataDomain:
    q = select(DataDomain).where(DataDomain.tenant == tenant, DataDomain.name == name)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("domain already exists")
    dom = DataDomain(tenant=tenant, name=name, owner=owner, description=description or "")
    db.add(dom)
    await db.flush()
    return dom
