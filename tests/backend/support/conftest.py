import os
import sys

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_support.db")
os.environ.setdefault("TESTING", "true")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.workflow import models as _wf  # noqa: E402,F401  (resolves workflow_versions FK targets)
