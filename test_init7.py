"""Test with TimestampMixin-like defaults."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, inspect as sa_inspect, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

@event.listens_for(Base, 'init', propagate=True)
def receive_init(target, args, kwargs):
    mapper = sa_inspect(target.__class__)
    for col in mapper.columns:
        key = col.key
        if col.default is not None and key not in kwargs:
            if key in target.__dict__ and target.__dict__[key] is not None:
                continue
            default_val = col.default.arg
            if callable(default_val):
                try:
                    target.__dict__[key] = default_val()
                except Exception:
                    pass
            else:
                target.__dict__[key] = default_val

class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

class User(Base, TimestampMixin):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default='free', nullable=False)

u = User(email='test')
print(f'is_active={u.is_active!r}, plan={u.plan!r}')
print(f'id={u.id!r}')
print(f'created_at={u.created_at!r}')
