"""Test overriding __init__ in Base."""
from sqlalchemy import Boolean, String, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Apply column defaults for any attributes still None
        mapper = sa_inspect(self.__class__)
        for col in mapper.columns:
            if col.default is not None and not callable(col.default.arg):
                key = col.key
                if getattr(self, key, None) is None:
                    setattr(self, key, col.default.arg)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

u = User(email='test')
print(f'is_active={u.is_active!r}')
