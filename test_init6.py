"""Set defaults via __dict__ to bypass SA descriptor."""
from sqlalchemy import Boolean, String, inspect as sa_inspect, event
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

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default='free', nullable=False)

u = User(email='test')
print(f'is_active={u.is_active!r}, plan={u.plan!r}')

# Verify it also works with keyword overrides
u2 = User(email='test2', is_active=False)
print(f'u2: is_active={u2.is_active!r}, plan={u2.plan!r}')

# Verify id and timestamps are still None (they have callable defaults)
print(f'id={u.id!r}')
