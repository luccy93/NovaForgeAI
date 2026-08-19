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
    CodeFile, CodeSymbol, FileStatus, SymbolType,
)
from app.code_intelligence.repository_summary import RepositorySummarizer


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


def _file(repo_id, idx, path, name, content, language="python"):
    return CodeFile(
        index_id=idx, repository_id=repo_id, file_path=path, file_name=name,
        language=language, status=FileStatus.PARSED.value, content=content,
        file_hash="h", size_bytes=len(content), line_count=content.count("\n") + 1,
    )


@pytest.mark.asyncio
async def test_detect_languages(db_session, repo_id):
    idx = uuid.uuid4()
    db_session.add_all([
        _file(repo_id, idx, "app/a.py", "a.py", "x=1", "python"),
        _file(repo_id, idx, "src/b.ts", "b.ts", "let y=1", "typescript"),
    ])
    await db_session.flush()
    summarizer = RepositorySummarizer(db_session)
    langs = await summarizer.detect_languages(repo_id)
    names = {l.language for l in langs}
    assert "python" in names and "typescript" in names


@pytest.mark.asyncio
async def test_detect_entry_points(db_session, repo_id):
    idx = uuid.uuid4()
    db_session.add(_file(repo_id, idx, "app/main.py", "main.py",
                         'if __name__ == "__main__":\n    main()\n', "python"))
    await db_session.flush()
    summarizer = RepositorySummarizer(db_session)
    eps = await summarizer.detect_entry_points(repo_id)
    assert isinstance(eps, list)


@pytest.mark.asyncio
async def test_generate_summary(db_session, repo_id):
    idx = uuid.uuid4()
    db_session.add_all([
        _file(repo_id, idx, "app/a.py", "a.py", "def foo():\n    pass\n", "python"),
        _file(repo_id, idx, "README.md", "README.md", "# Title\n", "markdown"),
    ])
    await db_session.flush()
    summarizer = RepositorySummarizer(db_session)
    summary = await summarizer.generate_summary(repo_id)
    assert summary is not None
    assert hasattr(summary, "languages") or hasattr(summary, "language_count")


@pytest.mark.asyncio
async def test_get_repository_profile(db_session, repo_id):
    idx = uuid.uuid4()
    db_session.add(_file(repo_id, idx, "app/a.py", "a.py", "x=1", "python"))
    await db_session.flush()
    summarizer = RepositorySummarizer(db_session)
    profile = await summarizer.get_repository_profile(repo_id)
    assert profile is not None
