import os
import sys
import uuid
import logging

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.ERROR)

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_ai_dev.db")
os.environ.setdefault("TESTING", "true")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))

from app.core.database import Base, async_engine, async_session  # noqa: E402
from app.ai_dev import models as _ai  # noqa: E402,F401
from app.code_intelligence import models as _ci  # noqa: E402,F401
from app.workflow import models as _wf  # noqa: E402,F401
from app.automation import models as _auto  # noqa: E402,F401
from app.iam import models as _iam  # noqa: E402,F401
from app.models import repository as _repo  # noqa: E402,F401
from app.delivery import models as _delivery  # noqa: E402,F401
from app.models import user as _user  # noqa: E402,F401


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
        try:
            from sqlalchemy import text

            async with async_engine.begin() as conn2:
                for tbl in reversed(Base.metadata.sorted_tables):
                    if (
                        tbl.name.startswith("code_")
                        or tbl.name == "repositories"
                        or tbl.name == "branches"
                        or tbl.name == "commits"
                        or tbl.name == "repository_versions"
                        or tbl.name.startswith("delivery_")
                    ):
                        await conn2.execute(text(f"DELETE FROM \"{tbl.name}\""))
        except Exception:
            pass


@pytest.fixture
def org_id():
    return str(uuid.uuid4())


@pytest.fixture
def other_org_id():
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def make_repo(db):
    """Factory: returns a Repository bound to org_id."""

    async def _make(org: str, name: str = "acme/service") -> dict:
        repo_id = uuid.uuid4()
        repo = _repo.Repository(
            id=repo_id,
            organization_id=uuid.UUID(org),
            name=name,
            full_name=f"{name}",
            default_branch="main",
            private=True,
        )
        db.add(repo)
        await db.flush()
        return {"repo_id": str(repo.id), "repo": repo}

    return _make


@pytest_asyncio.fixture
async def seed_index(db):
    """Factory: builds a CodeIndex + CodeFile + symbols/chunks for a repo."""

    async def _seed(repo_id: str, symbols: list[tuple[str, str, int, int]] | None = None,
                    chunks: list[tuple[str, int, int]] | None = None,
                    files: list[tuple[str, str, str]] | None = None) -> dict:
        rid = uuid.UUID(repo_id)
        from datetime import datetime, timezone

        idx = _ci.CodeIndex(
            repository_id=rid,
            status=_ci.IndexStatus.READY.value,
            commit_sha="abc123",
            files_total=1,
            files_processed=1,
            symbols_extracted=2,
            chunks_created=1,
            embedding_model="mock-embed-1",
            embedding_version="1.0",
            embedding_dimension=128,
        )
        db.add(idx)
        await db.flush()

        fid = uuid.uuid4()
        file_rows = files or [("src/main.py", "main.py", "python")]
        f = _ci.CodeFile(
            id=fid,
            index_id=idx.id,
            repository_id=rid,
            file_path=file_rows[0][0],
            file_name=file_rows[0][1],
            language=file_rows[0][2],
            line_count=10,
            size_bytes=512,
        )
        db.add(f)
        await db.flush()

        created_symbols = []
        for name, stype, start, end in (symbols or [("main", "FUNCTION", 1, 10)]):
            sym = _ci.CodeSymbol(
                repository_id=rid,
                index_id=idx.id,
                file_id=f.id,
                symbol_id=f"{rid}-{name}-{stype}",
                symbol_type=stype,
                name=name,
                qualified_name=name,
                start_line=start,
                end_line=end,
                signature=f"def {name}(x):",
            )
            db.add(sym)
            created_symbols.append(sym)
        await db.flush()

        created_chunks = []
        for content, start, end in (chunks or [("def main(x): return x", 1, 10)]):
            ch = _ci.CodeChunk(
                repository_id=rid,
                index_id=idx.id,
                file_id=f.id,
                chunk_type="CODE",
                content=content,
                start_line=start,
                end_line=end,
                language="python",
            )
            db.add(ch)
            created_chunks.append(ch)
        await db.flush()
        return {"index_id": str(idx.id), "file_id": str(f.id), "file": f,
                "symbols": created_symbols, "chunks": created_chunks}

    return _seed


class FakeUser:
    def __init__(self, org: str, role: str = "admin"):
        self.id = uuid.uuid4()
        self.organization_id = uuid.UUID(org)
        self.role = role


@pytest_asyncio.fixture
async def api_client(db):
    """Isolated ASGI app exposing only the ai-dev router with auth stubbed."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.ai_dev import router as ai_dev_router
    from app.api.auth import _get_current_user
    from app.core.database import get_db

    app = FastAPI()
    app.include_router(ai_dev_router, prefix="/api/v1")

    holder = {"user": FakeUser(str(uuid.uuid4()))}

    async def _current_user():
        return holder["user"]

    async def _override_get_db():
        yield db

    app.dependency_overrides[_get_current_user] = _current_user
    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac._app = app
        ac._user_holder = holder
        yield ac