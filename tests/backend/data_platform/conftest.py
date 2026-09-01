import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_data_platform.db")
os.environ.setdefault("TESTING", "true")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, async_engine, async_session
from app.workflow import models as _wf  # noqa: E402,F401
from app.data_platform import models as _dp  # noqa: F401
from app.data_platform import models_lakehouse as _lh  # noqa: F401
from app.iam import models as _iam  # noqa: F401
from app.regions import models as _regions  # noqa: F401


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        yield session
        await session.rollback()
        # cleanup data_platform tables
        try:
            from sqlalchemy import text
            async with async_engine.begin() as conn2:
                for tbl in reversed(Base.metadata.sorted_tables):
                    if tbl.name.startswith("data_"):
                        await conn2.execute(text(f'DELETE FROM "{tbl.name}"'))
        except Exception:
            pass


@pytest.fixture
def org_id():
    import uuid
    return str(uuid.uuid4())


@pytest.fixture
def other_org_id():
    import uuid
    return str(uuid.uuid4())
