import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TESTING", "true")

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

from app.core.database import Base
from app.code_intelligence.models import (
    CodeFile, CodeSymbol, CodeIndex, FileStatus, IndexStatus, SymbolType,
)
from app.code_intelligence.consistency import ConsistencyValidator


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_mappers()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
def repo_id():
    return uuid.uuid4()


def _file(repo_id, idx, path, name, content="x=1"):
    return CodeFile(
        index_id=idx, repository_id=repo_id, file_path=path, file_name=name,
        language="python", status=FileStatus.PARSED.value, content=content,
        file_hash="h", size_bytes=len(content), line_count=content.count("\n") + 1,
    )


@pytest.mark.asyncio
async def test_validate_all_empty(db_session, repo_id):
    validator = ConsistencyValidator()
    report = await validator.validate_all(repo_id, db_session)
    assert report is not None
    # Empty repository should be perfectly consistent.
    assert report.health_score == 100.0


@pytest.mark.asyncio
async def test_health_score(db_session, repo_id):
    validator = ConsistencyValidator()
    score = await validator.get_health_score(repo_id, db_session)
    assert 0.0 <= score <= 100.0
    assert score == 100.0


@pytest.mark.asyncio
async def test_repair_suggestions(db_session, repo_id):
    validator = ConsistencyValidator()
    suggestions = await validator.get_repair_suggestions(repo_id, db_session)
    assert isinstance(suggestions, list)


@pytest.mark.asyncio
async def test_validate_with_symbols(db_session, repo_id):
    idx = uuid.uuid4()
    f = _file(repo_id, idx, "app/mod.py", "mod.py", "def foo():\n    pass\n")
    db_session.add(f)
    await db_session.flush()
    sym = CodeSymbol(
        file_id=f.id, index_id=idx, repository_id=repo_id, name="foo",
        symbol_type=SymbolType.FUNCTION.value, symbol_id="app.mod.foo",
        qualified_name="app.mod.foo", language="python",
    )
    db_session.add(sym)
    await db_session.flush()
    validator = ConsistencyValidator()
    report = await validator.validate_all(repo_id, db_session)
    assert report is not None
    assert 0.0 <= report.health_score <= 100.0
