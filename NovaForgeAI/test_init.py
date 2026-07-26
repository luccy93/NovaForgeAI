"""Peek at SQLAlchemy generated __init__."""
import dis
from sqlalchemy import Boolean, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

# Get the source of the generated __init__
try:
    import inspect as std_inspect
    source = std_inspect.getsource(User.__init__)
    print("SOURCE:")
    print(source)
except:
    print("Cannot get source")

# Disassemble
print("BYTECODE:")
try:
    dis.dis(User.__init__)
except Exception as e:
    print(f"Error: {e}")
