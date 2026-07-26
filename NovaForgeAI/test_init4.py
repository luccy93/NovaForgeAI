"""Debug the init event more carefully."""
from sqlalchemy import Boolean, String, inspect as sa_inspect, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

@event.listens_for(Base, 'init', propagate=True)
def receive_init(target, args, kwargs):
    print(f"INIT EVENT FIRED: {target.__class__.__name__}")

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

print("Creating user...")
u = User(email='test')
print(f'is_active={u.is_active!r}')
