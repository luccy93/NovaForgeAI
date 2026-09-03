import os
import sys
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_novaforge.db")
os.environ.setdefault("TESTING", "true")


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, async_engine, async_session
from app.workflow import models as _wf  # noqa: E402,F401
from app.knowledge import models as _knowledge  # noqa: F401


@pytest_asyncio.fixture
async def db():
    async with async_session() as session:
        yield session
        await session.rollback()
        try:
            from sqlalchemy import text
            async with async_engine.begin() as conn:
                for tbl in reversed(Base.metadata.sorted_tables):
                    if tbl.name.startswith("knowledge_"):
                        await conn.execute(text(f'DELETE FROM "{tbl.name}"'))
        except Exception:
            pass


@pytest.fixture
def org_id():
    return str(uuid.uuid4())


@pytest.fixture
def fake_user(org_id):
    class _User:
        id = str(uuid.uuid4())
        organization_id = org_id
        role = "admin"
        classification_clearance = 3
    return _User()


@pytest_asyncio.fixture
async def api_client():
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app
    from app.core.database import get_db

    app = create_app()

    async def _override_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client._app = app
        yield client
