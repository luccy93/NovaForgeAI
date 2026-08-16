"""Generic repository helpers for SRE entities.

Provides small async CRUD utilities so SRE modules stay declarative and
consistent (tenant isolation, pagination, sorting, id generation).
"""

import uuid
from typing import Any, Optional, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

T = TypeVar("T", bound=Base)

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 500


def new_id() -> str:
    return uuid.uuid4().hex


def new_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:24]}"


def pagination(offset: int, limit: int) -> tuple[int, int]:
    return max(offset, 0), max(1, min(limit or PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX))


async def get_by_id(db: AsyncSession, model: Type[T], entity_id: str) -> Optional[T]:
    result = await db.execute(select(model).where(model.id == entity_id))
    return result.scalar_one_or_none()


async def get_one(db: AsyncSession, model: Type[T], **filters: Any) -> Optional[T]:
    stmt = select(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_all(
    db: AsyncSession,
    model: Type[T],
    *,
    offset: int = 0,
    limit: int = PAGE_SIZE_DEFAULT,
    order_by: Optional[str] = None,
    descending: bool = True,
    **filters: Any,
) -> tuple[list[T], int]:
    stmt = select(model)
    for column, value in filters.items():
        if value is not None and value != "":
            stmt = stmt.where(getattr(model, column) == value)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    if order_by:
        column = getattr(model, order_by, None)
        if column is not None:
            stmt = stmt.order_by(column.desc() if descending else column.asc())
    offset, limit = pagination(offset, limit)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def create(db: AsyncSession, model: Type[T], **values: Any) -> T:
    entity = model(**values)
    db.add(entity)
    await db.flush()
    return entity


async def update(db: AsyncSession, entity: Base, **values: Any) -> Base:
    for key, value in values.items():
        if hasattr(entity, key):
            setattr(entity, key, value)
    await db.flush()
    return entity


async def delete(db: AsyncSession, entity: Base) -> None:
    await db.delete(entity)
    await db.flush()
