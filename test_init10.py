"""Working solution for applying column defaults."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, inspect as sa_inspect, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.schema import ScalarElementColumnDefault, CallableColumnDefault

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
            if isinstance(col.default, CallableColumnDefault):
                target.__dict__[key] = col.default(None)
            elif isinstance(col.default, ScalarElementColumnDefault):
                target.__dict__[key] = col.default.arg

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
print(f'id={u.id!r}, created_at={u.created_at!r}')
print(f'is_active={u.is_active!r}, plan={u.plan!r}')

# With override
u2 = User(email='test2', is_active=False)
print(f'u2: is_active={u2.is_active!r}')
