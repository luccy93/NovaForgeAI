"""Investigate CallableColumnDefault more."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.schema import ScalarElementColumnDefault, CallableColumnDefault

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

class User(Base, TimestampMixin):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

mapper = sa_inspect(User)
for col in mapper.columns:
    if col.default is not None:
        print(f'col={col.key}: default type={type(col.default).__name__}')
        if isinstance(col.default, CallableColumnDefault):
            print(f'  arg: {col.default.arg!r}')
            print(f'  arg type: {type(col.default.arg)}')
            print(f'  arg is uuid.uuid4: {col.default.arg is uuid.uuid4}')
            # Try calling it
            import inspect as std_inspect
            sig = std_inspect.signature(col.default.arg)
            print(f'  arg sig: {sig}')
            try:
                result = col.default.arg()
                print(f'  arg() result: {result!r}')
            except Exception as e:
                print(f'  arg() error: {e}')
        elif isinstance(col.default, ScalarElementColumnDefault):
            print(f'  arg: {col.default.arg!r}')
