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
    CodeFile, CodeChunk, CodeSymbol, FileStatus, SymbolType,
)
from app.code_intelligence.documentation import DocumentationExtractor


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


def _file(repo_id, idx, path, name, content, is_doc=False, language=None):
    return CodeFile(
        index_id=idx, repository_id=repo_id, file_path=path, file_name=name,
        language=language, status=FileStatus.PARSED.value, is_documentation=is_doc,
        content=content, file_hash="h", size_bytes=len(content), line_count=content.count("\n") + 1,
    )


def _chunk(repo_id, idx, file_id, content, chunk_type="file_content"):
    return CodeChunk(
        repository_id=repo_id, index_id=idx, file_id=file_id, chunk_type=chunk_type,
        content=content, language="python", start_line=1, end_line=1,
        token_count=len(content),
    )


@pytest.mark.asyncio
async def test_extract_readme(db_session, repo_id):
    idx = uuid.uuid4()
    f = _file(repo_id, idx, "README.md", "README.md",
              "# My Project\n\n## Install\npip install.\n## Usage\nrun it.\n", is_doc=True)
    db_session.add(f)
    await db_session.flush()
    db_session.add(_chunk(repo_id, idx, f.id,
                          "# My Project\n\n## Install\npip install.\n## Usage\nrun it.\n"))
    await db_session.flush()
    ext = DocumentationExtractor(db_session)
    readmes = await ext.extract_readme(repo_id, db_session)
    assert len(readmes) == 1
    assert "My Project" in readmes[0].raw_content


@pytest.mark.asyncio
async def test_extract_docstrings(db_session, repo_id):
    idx = uuid.uuid4()
    content = 'def foo():\n    """Does foo."""\n    pass\n'
    f = _file(repo_id, idx, "app/mod.py", "mod.py", content, language="python")
    db_session.add(f)
    await db_session.flush()
    sym = CodeSymbol(
        file_id=f.id, index_id=idx, repository_id=repo_id, name="foo",
        symbol_type=SymbolType.FUNCTION.value, symbol_id="app.mod.foo",
        qualified_name="app.mod.foo", language="python", docstring="Does foo.",
        start_line=1, end_line=2,
    )
    db_session.add(sym)
    await db_session.flush()
    ext = DocumentationExtractor(db_session)
    docs = await ext.extract_docstrings(f.id, content, "python", db_session)
    assert len(docs) >= 1
    assert "Does foo" in docs[0].docstring


@pytest.mark.asyncio
async def test_documentation_coverage(db_session, repo_id):
    idx = uuid.uuid4()
    content = 'def foo():\n    """Doc."""\n    pass\ndef bar():\n    pass\n'
    f = _file(repo_id, idx, "app/mod.py", "mod.py", content, language="python")
    db_session.add(f)
    await db_session.flush()
    sym1 = CodeSymbol(
        file_id=f.id, index_id=idx, repository_id=repo_id, name="foo",
        symbol_type=SymbolType.FUNCTION.value, symbol_id="app.mod.foo",
        qualified_name="app.mod.foo", language="python", docstring="Doc.", start_line=1, end_line=1,
    )
    sym2 = CodeSymbol(
        file_id=f.id, index_id=idx, repository_id=repo_id, name="bar",
        symbol_type=SymbolType.FUNCTION.value, symbol_id="app.mod.bar",
        qualified_name="app.mod.bar", language="python", start_line=2, end_line=2,
    )
    db_session.add_all([sym1, sym2])
    await db_session.flush()
    ext = DocumentationExtractor(db_session)
    coverage = await ext.get_documentation_coverage(repo_id, db_session)
    assert hasattr(coverage, "total_symbols")
    assert coverage.total_symbols >= 1


@pytest.mark.asyncio
async def test_documentation_summary(db_session, repo_id):
    idx = uuid.uuid4()
    f = _file(repo_id, idx, "README.md", "README.md", "# Title\n## API\n", is_doc=True)
    db_session.add(f)
    await db_session.flush()
    db_session.add(_chunk(repo_id, idx, f.id, "# Title\n## API\n"))
    await db_session.flush()
    ext = DocumentationExtractor(db_session)
    summary = await ext.get_documentation_summary(repo_id, db_session)
    assert summary is not None
    assert hasattr(summary, "readme_files")
