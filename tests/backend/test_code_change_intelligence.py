import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TESTING", "true")

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

from app.core.database import Base
from app.code_intelligence.models import CodeHistory, CodeFile, FileStatus
from app.code_intelligence.change_intelligence import ChangeAnalyzer


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


def _history(repo_id, path, commits, file_id=None):
    file_id = file_id or uuid.uuid4()
    rows = []
    now = datetime.now(timezone.utc)
    for i, (email, days, added, deleted) in enumerate(commits, 1):
        rows.append(CodeHistory(
            repository_id=repo_id, file_id=file_id, file_path=path,
            commit_sha=f"sha{path}-{i}", author_email=email, author_name=email.split("@")[0].title(),
            commit_date=now - timedelta(days=days), change_type="M",
            lines_added=added, lines_deleted=deleted,
        ))
    return rows


@pytest.mark.asyncio
async def test_detect_hotspots(db_session, repo_id):
    core_id = uuid.uuid4()
    db_session.add_all(_history(repo_id, "app/core.py", [
        ("alice@x.com", 1, 100, 10), ("alice@x.com", 2, 50, 5), ("bob@x.com", 3, 30, 2),
    ], file_id=core_id))
    db_session.add_all(_history(repo_id, "app/util.py", [("carol@x.com", 5, 20, 1)], file_id=uuid.uuid4()))
    await db_session.flush()

    analyzer = ChangeAnalyzer(db_session)
    hotspots = await analyzer.detect_hotspots(repo_id, db_session, top_n=10)
    assert len(hotspots) == 2
    assert hotspots[0].file_path == "app/core.py"
    assert hotspots[0].change_count == 3
    assert hotspots[0].unique_authors == 2


@pytest.mark.asyncio
async def test_get_change_frequency(db_session, repo_id):
    db_session.add_all(_history(repo_id, "app/core.py", [
        ("alice@x.com", 1, 100, 10), ("alice@x.com", 5, 50, 5),
    ], file_id=uuid.uuid4()))
    await db_session.flush()
    analyzer = ChangeAnalyzer(db_session)
    freq = await analyzer.get_change_frequency(repo_id, db_session, days=90)
    assert len(freq) == 1
    assert freq[0].file_path == "app/core.py"
    assert freq[0].total_changes == 2


@pytest.mark.asyncio
async def test_get_recent_modifications(db_session, repo_id):
    db_session.add_all(_history(repo_id, "app/core.py", [("alice@x.com", 1, 100, 10)]))
    db_session.add_all(_history(repo_id, "app/old.py", [("bob@x.com", 200, 10, 1)]))
    await db_session.flush()
    analyzer = ChangeAnalyzer(db_session)
    recent = await analyzer.get_recent_modifications(repo_id, db_session, days=30)
    paths = {r.file_path for r in recent}
    assert "app/core.py" in paths
    assert "app/old.py" not in paths


@pytest.mark.asyncio
async def test_detect_stale_files(db_session, repo_id):
    db_session.add_all(_history(repo_id, "app/core.py", [("alice@x.com", 1, 100, 10)]))
    db_session.add_all(_history(repo_id, "app/stale.py", [("bob@x.com", 400, 10, 1)]))
    await db_session.flush()
    analyzer = ChangeAnalyzer(db_session)
    stale = await analyzer.detect_stale_files(repo_id, db_session, stale_days=180)
    paths = {s.file_path for s in stale}
    assert "app/stale.py" in paths
    assert "app/core.py" not in paths


@pytest.mark.asyncio
async def test_get_change_summary(db_session, repo_id):
    db_session.add_all(_history(repo_id, "app/core.py", [
        ("alice@x.com", 1, 100, 10), ("bob@x.com", 2, 50, 5),
    ]))
    await db_session.flush()
    analyzer = ChangeAnalyzer(db_session)
    summary = await analyzer.get_change_summary(repo_id, db_session)
    assert summary.total_commits == 2
    assert summary.unique_authors == 2
    assert summary.total_lines_changed == 165
    assert isinstance(summary.top_hotspots, list)
