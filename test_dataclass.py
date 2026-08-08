"""Test SQLAlchemy dataclass integration."""
from sqlalchemy import Boolean, String, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm import registry

reg = registry()

@reg.mapped_as_dataclass
class Base:
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default='free', nullable=False)

u = User(email='test')
print(f'is_active={u.is_active!r}, plan={u.plan!r}')
