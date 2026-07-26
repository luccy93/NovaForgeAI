"""Debug the init event more carefully with prints."""
from sqlalchemy import Boolean, String, inspect as sa_inspect, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

@event.listens_for(Base, 'init', propagate=True)
def receive_init(target, args, kwargs):
    print(f"INIT EVENT FIRED: {target.__class__.__name__}")
    print(f"  kwargs: {kwargs}")
    try:
        mapper = sa_inspect(target.__class__)
        for col in mapper.columns:
            key = col.key
            val = getattr(target, key, 'NOT_SET')
            print(f"  col={key}, default={col.default}, val={val!r}")
            if col.default is not None:
                if val is None or val == 'NOT_SET':
                    default_val = col.default.arg
                    print(f"    would set to: {default_val!r}")
                    if not callable(default_val):
                        setattr(target, key, default_val)
                    else:
                        try:
                            setattr(target, key, default_val())
                        except Exception as e:
                            print(f"    callable default failed: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

print("Creating user...")
u = User(email='test')
print(f'Result: is_active={u.is_active!r}')
