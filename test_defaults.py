"""Test SQLAlchemy 2.0 default behavior."""
from sqlalchemy import Boolean, String, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

print(f'User.__init__: {User.__init__}')
print(f'Is callable: {callable(User.__init__)}')

# Check what happens with init
u = User(email='test')
print(f'is_active after User(email="test"): {u.is_active!r}')

# Check column default
mapper = sa_inspect(User)
for col in mapper.columns:
    print(f'Column {col.key}: default={col.default}')

# What if we don't pass any kwargs that need defaults?
u2 = User()
print(f'User() is_active: {u2.is_active!r}, email: {u2.email!r}')

# Check if the default applies when attribute is not set
u3 = User.__new__(User)
print(f'is_active pre-init: {getattr(u3, "is_active", "NOT SET")!r}')
User.__init__(u3, email='test3')
print(f'is_active post-init: {u3.is_active!r}')
