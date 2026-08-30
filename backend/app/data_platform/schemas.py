"""Schema registry — immutable published schemas."""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataSchema, DataSchemaVersion

COMPATIBILITY = {"backward", "forward", "full"}


async def publish_schema(db: AsyncSession, tenant: str, dataset_id: str, payload: dict) -> DataSchema:
    try:
        did = uuid.UUID(dataset_id)
    except Exception:
        raise ValueError("invalid dataset_id")
    version = payload.get("version") or "1.0"
    fields = payload.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("fields list required")
    # Check existing published immutable: cannot overwrite same version
    q = select(DataSchema).where(DataSchema.dataset_id == did, DataSchema.version == version)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("schema version already published — immutable")
    schema = DataSchema(
        dataset_id=did,
        tenant=tenant,
        version=version,
        fields=fields,
        types={f["name"]: f["type"] for f in fields if "name" in f and "type" in f},
        classification=(payload.get("classification") or "INTERNAL").upper(),
        is_published=True,
    )
    db.add(schema)
    await db.flush()
    return schema


async def get_schema(db: AsyncSession, tenant: str, schema_id: str) -> DataSchema | None:
    try:
        sid = uuid.UUID(schema_id)
        q = select(DataSchema).where(DataSchema.id == sid, DataSchema.tenant == tenant)
        res = await db.execute(q)
        return res.scalar_one_or_none()
    except Exception:
        return None


async def list_schemas(db: AsyncSession, tenant: str, dataset_id: str | None = None, limit: int = 50) -> list[DataSchema]:
    q = select(DataSchema).where(DataSchema.tenant == tenant)
    if dataset_id:
        try:
            did = uuid.UUID(dataset_id)
            q = q.where(DataSchema.dataset_id == did)
        except Exception:
            pass
    q = q.order_by(DataSchema.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def evolve_schema(db: AsyncSession, tenant: str, schema_id: str, new_fields: list, compatibility: str = "backward") -> DataSchema:
    if compatibility not in COMPATIBILITY:
        raise ValueError("invalid compatibility")
    schema = await get_schema(db, tenant, schema_id)
    if not schema:
        raise ValueError("schema not found")
    if not schema.is_published:
        raise ValueError("only published schemas can be evolved")
    # Check compatible changes: only add field allowed for backward, for full any
    old_names = {f["name"] for f in schema.fields}
    new_names = {f["name"] for f in new_fields}
    removed = old_names - new_names
    if removed and compatibility in ("backward", "full"):
        raise ValueError(f"incompatible: removed fields {removed}")
    # Type changes check
    old_types = {f["name"]: f["type"] for f in schema.fields}
    for f in new_fields:
        if f["name"] in old_types and f["type"] != old_types[f["name"]]:
            # Allow int->float, string->json as compatible
            if not ((old_types[f["name"]] == "int" and f["type"] == "float") or (old_types[f["name"]] == "string" and f["type"] == "json")):
                if compatibility != "full":
                    raise ValueError(f"incompatible type change {f['name']}: {old_types[f['name']]} -> {f['type']}")
    # Create new version
    try:
        major, minor = schema.version.split(".")
        new_version = f"{major}.{int(minor)+1}"
    except Exception:
        new_version = schema.version + ".1"
    new_schema = DataSchema(
        dataset_id=schema.dataset_id,
        tenant=tenant,
        version=new_version,
        fields=new_fields,
        types={f["name"]: f["type"] for f in new_fields},
        classification=schema.classification,
        is_published=True,
    )
    db.add(new_schema)
    # Record version diff
    ver = DataSchemaVersion(
        schema_id=schema.id,
        tenant=tenant,
        version=new_version,
        diff={"added": list(new_names - old_names), "removed": list(removed)},
        compatibility=compatibility,
    )
    db.add(ver)
    await db.flush()
    return new_schema
