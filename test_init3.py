"""Test overriding __init__ more carefully."""
from sqlalchemy import Boolean, String, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import event

class Base(DeclarativeBase):
    pass

# Use the 'init' event on Base to apply defaults after construction
@event.listens_for(Base, 'init', propagate=True)
def receive_init(target, args, kwargs):
    """Apply column defaults for any attributes still None."""
    try:
        mapper = sa_inspect(target.__class__)
        for col in mapper.columns:
            if col.default is not None:
                key = col.key
                val = getattr(target, key, None)
                if val is None:
                    default = col.default.arg
                    if not callable(default):
                        setattr(target, key, default)
                    else:
                        try:
                            setattr(target, key, default())
                        except Exception:
                            pass
    except Exception:
        pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

u = User(email='test')
print(f'is_active={u.is_active!r}')
