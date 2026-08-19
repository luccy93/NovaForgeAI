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
from app.code_intelligence.models import CodeFile, CodeSymbol, CodeTest, FileStatus, SymbolType
from app.code_intelligence.test_intelligence import TestDetector


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


def _file(repo_id, idx_id, path, name, content, is_test=False, language="python"):
    return CodeFile(
        index_id=idx_id, repository_id=repo_id, file_path=path, file_name=name,
        language=language, status=FileStatus.PARSED.value, is_test_file=is_test,
        content=content, file_hash="h", size_bytes=len(content), line_count=content.count("\n") + 1,
    )


@pytest.mark.asyncio
async def test_detect_test_files(db_session, repo_id):
    idx = uuid.uuid4()
    db_session.add(_file(repo_id, idx, "tests/test_core.py", "test_core.py",
                         "def test_a():\n    pass\n", is_test=True))
    db_session.add(_file(repo_id, idx, "app/core.py", "core.py", "def foo():\n    pass\n"))
    await db_session.flush()
    detector = TestDetector()
    files = await detector.detect_test_files(repo_id, db_session)
    assert len(files) == 1
    assert files[0].file_path == "tests/test_core.py"
    assert files[0].detected_framework in (None, "pytest")


@pytest.mark.asyncio
async def test_extract_tests(db_session, repo_id):
    idx = uuid.uuid4()
    fid = uuid.uuid4()
    f = CodeFile(
        index_id=idx, repository_id=repo_id, file_path="tests/test_x.py", file_name="test_x.py",
        language="python", status=FileStatus.PARSED.value, is_test_file=True, file_hash="h",
        size_bytes=10, line_count=3,
    )
    db_session.add(f)
    await db_session.flush()
    detector = TestDetector()
    records = await detector.extract_tests(
        fid, "tests/test_x.py",
        "def test_foo():\n    assert True\ndef test_bar():\n    assert False\n",
        "python", db_session,
    )
    assert len(records) == 2
    names = {r.test_name for r in records}
    assert "test_foo" in names and "test_bar" in names


@pytest.mark.asyncio
async def test_mark_test_files(db_session, repo_id):
    idx = uuid.uuid4()
    f = _file(repo_id, idx, "tests/test_y.py", "test_y.py", "def test_z():\n    pass\n", is_test=False)
    db_session.add(f)
    await db_session.flush()
    detector = TestDetector()
    count = await detector.mark_test_files(repo_id, db_session)
    assert count == 1
    await db_session.refresh(f)
    assert f.is_test_file is True


@pytest.mark.asyncio
async def test_map_tests_to_sources(db_session, repo_id):
    idx = uuid.uuid4()
    src = CodeFile(
        index_id=idx, repository_id=repo_id, file_path="app/user.py", file_name="user.py",
        language="python", status=FileStatus.PARSED.value, is_test_file=False, content="def create_user():\n    pass\n",
        file_hash="h", size_bytes=10, line_count=2,
    )
    src_sym = CodeSymbol(
        file_id=None, index_id=idx, repository_id=repo_id, name="create_user",
        symbol_type=SymbolType.FUNCTION.value, symbol_id="app.user.create_user",
        qualified_name="app.user.create_user", language="python",
    )
    test = CodeFile(
        index_id=idx, repository_id=repo_id, file_path="tests/test_user.py", file_name="test_user.py",
        language="python", status=FileStatus.PARSED.value, is_test_file=True,
        content="def test_create_user():\n    pass\n", file_hash="h", size_bytes=10, line_count=2,
    )
    db_session.add_all([src, test])
    await db_session.flush()
    src_sym.file_id = src.id
    db_session.add(src_sym)
    code_test = CodeTest(
        repository_id=repo_id, file_id=test.id, test_type="unit",
        test_name="test_create_user", framework="pytest",
    )
    db_session.add(code_test)
    await db_session.flush()
    detector = TestDetector()
    mappings = await detector.map_tests_to_sources(repo_id, db_session)
    assert isinstance(mappings, list)
    assert len(mappings) >= 1
    assert mappings[0].test_name == "test_create_user"
