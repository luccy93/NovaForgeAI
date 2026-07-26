"""Debug - why are TimestampMixin defaults not applying?"""
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
            in_dict = key in target.__dict__
            current = target.__dict__.get(key, 'NOT_IN_DICT')
            print(f"  col={key}: default={col.default!r}, in_dict={in_dict}, current={current!r}")
            if not in_dict or target.__dict__[key] is None:
                default_val = col.default.arg
                print(f"    would set to: {default_val}")
                if callable(default_val):
                    try:
                        target.__dict__[key] = default_val()
                        print(f"    set to: {target.__dict__[key]!r}")
                    except Exception as e:
                        print(f"    callable failed: {e}")
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

print("Creating user...")
u = User(email='test')
print(f'Results: id={u.id!r}, created_at={u.created_at!r}')
print(f'is_active={u.is_active!r}, plan={u.plan!r}')
