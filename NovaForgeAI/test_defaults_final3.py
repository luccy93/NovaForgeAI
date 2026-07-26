"""Try calling with None argument."""
import uuid
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.schema import CallableColumnDefault

class Base(DeclarativeBase):
    pass

class T(Base):
    __tablename__ = 't'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

mapper = sa_inspect(T)
col = [c for c in mapper.columns if c.key == 'id'][0]

# Try calling arg with different approaches
print(f'arg: {col.default.arg!r}')
try:
    result = col.default.arg(None)
    print(f'arg(None): {result!r}')
except Exception as e:
    print(f'arg(None) error: {e}')

try:
    result = col.default.arg(ctx=None)
    print(f'arg(ctx=None): {result!r}')
except Exception as e:
    print(f'arg(ctx=None) error: {e}')

# Check what the actual arg is
import dis
dis.dis(col.default.arg)
