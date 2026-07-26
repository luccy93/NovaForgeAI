"""Final approach for applying defaults."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, inspect as sa_inspect, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.schema import ScalarElementColumnDefault, CallableColumnDefault

class Base(DeclarativeBase):
    pass

# Investigate CallableColumnDefault
c = CallableColumnDefault(uuid.uuid4)
print(f'type: {type(c)}')
print(f'callable: {callable(c)}')
print(f'arg is uuid4: {c.arg is uuid.uuid4}')
print(f'arg callable: {callable(c.arg)}')

import inspect as std_inspect
try:
    sig = std_inspect.signature(c.arg)
    print(f'arg signature: {sig}')
except:
    print('no sig')
