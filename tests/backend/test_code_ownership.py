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
from app.code_intelligence.models import (
    CodeFile,
    CodeHistory,
    CodeOwnership,
    FileStatus,
)
from app.code_intelligence.ownership import OwnershipAnalyzer


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
async def repo_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
def analyzer():
    return OwnershipAnalyzer(half_life_days=180)


@pytest_asyncio.fixture
async def files_on_disk(db_session, repo_id):
    paths = ["app/core.py", "app/service.py", "app/auth.py", "tests/test_core.py", "docs/README.md"]
    created = []
    for p in paths:
        f = CodeFile(
            index_id=uuid.uuid4(), repository_id=repo_id, file_path=p,
            file_name=p.split("/")[-1], language="python", status=FileStatus.PARSED.value,
        )
        db_session.add(f)
        created.append(f)
    await db_session.flush()
    return created


@pytest.mark.asyncio
async def test_parse_codeowners(analyzer, repo_id):
    content = "# CODEOWNERS\n*.py    @alice @bob\napp/auth.py    @charlie\ntests/        @dave @eve\n"
    rules = analyzer.parse_codeowners(repo_id, content)
    assert len(rules) == 3
    patterns = {r.pattern for r in rules}
    assert "*.py" in patterns and "app/auth.py" in patterns and "tests/" in patterns
    py_rule = next(r for r in rules if r.pattern == "*.py")
    assert "alice" in py_rule.owners and "bob" in py_rule.owners


@pytest.mark.asyncio
async def test_derive_ownership(db_session, repo_id, analyzer, files_on_disk):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        CodeHistory(
            repository_id=repo_id, file_id=files_on_disk[0].id, file_path="app/core.py",
            commit_sha=f"sha{i:03d}", author_email=f"{name}@example.com", author_name=name.title(),
            commit_date=now - timedelta(days=d), lines_added=a, lines_deleted=dl,
        )
        for i, (name, d, a, dl) in enumerate([
            ("alice", 5, 100, 20), ("bob", 2, 50, 10), ("alice", 1, 30, 5),
        ], 1)
    ])
    await db_session.flush()

    records = await analyzer.derive_ownership_from_history(repo_id, db_session)
    assert len(records) >= 2
    emails = {o.owner_email for o in records}
    assert "alice@example.com" in emails
    assert "bob@example.com" in emails

    alice_rec = next(o for o in records if o.owner_email == "alice@example.com")
    assert alice_rec.commits_count == 2
    assert alice_rec.lines_changed == 155
    assert all(0.0 <= r.ownership_score <= 1.0 for r in records)


@pytest.mark.asyncio
async def test_identify_bus_risk(db_session, repo_id, analyzer, files_on_disk):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        CodeOwnership(
            repository_id=repo_id, file_path="app/core.py", owner_email="alice@example.com",
            owner_name="Alice", ownership_score=0.85, commits_count=20, lines_changed=500,
            last_commit_date=now - timedelta(days=3),
        ),
        CodeOwnership(
            repository_id=repo_id, file_path="app/service.py", owner_email="bob@example.com",
            owner_name="Bob", ownership_score=0.60, commits_count=5, lines_changed=100,
            last_commit_date=now - timedelta(days=60),
        ),
        CodeOwnership(
            repository_id=repo_id, file_path="app/auth.py", owner_email="charlie@example.com",
            owner_name="Charlie", ownership_score=0.70, commits_count=10, lines_changed=200,
            last_commit_date=now - timedelta(days=200),
        ),
    ])
    await db_session.flush()

    risk = await analyzer.identify_bus_risk(repo_id, db_session, threshold=1)
    assert len(risk) >= 2
    file_paths = {item.file_path for item in risk}
    assert "app/core.py" in file_paths
    assert "app/auth.py" in file_paths

    core = next(i for i in risk if i.file_path == "app/core.py")
    assert core.sole_owner_email == "alice@example.com"
    assert core.total_commits == 20

    auth = next(i for i in risk if i.file_path == "app/auth.py")
    assert auth.risk_level == "medium"


@pytest.mark.asyncio
async def test_get_contributor_stats(db_session, repo_id, analyzer, files_on_disk):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        CodeOwnership(
            repository_id=repo_id, file_path="app/core.py", owner_email="alice@example.com",
            owner_name="Alice", ownership_score=0.8, commits_count=15, lines_changed=300,
            last_commit_date=now - timedelta(days=2),
        ),
        CodeOwnership(
            repository_id=repo_id, file_path="app/service.py", owner_email="alice@example.com",
            owner_name="Alice", ownership_score=0.6, commits_count=10, lines_changed=200,
            last_commit_date=now - timedelta(days=5),
        ),
        CodeOwnership(
            repository_id=repo_id, file_path="app/service.py", owner_email="bob@example.com",
            owner_name="Bob", ownership_score=0.5, commits_count=8, lines_changed=150,
            last_commit_date=now - timedelta(days=10),
        ),
    ])
    await db_session.flush()

    stats = await analyzer.get_contributor_stats(repo_id, db_session)
    alice = stats["alice@example.com"]
    assert alice.total_commits == 25
    assert alice.files_touched == 2
    assert alice.total_lines_changed == 500

    bob = stats["bob@example.com"]
    assert bob.total_commits == 8
    assert bob.files_touched == 1


@pytest.mark.asyncio
async def test_get_ownership_summary(db_session, repo_id, analyzer, files_on_disk):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        CodeOwnership(
            repository_id=repo_id, file_path="app/core.py", owner_email="alice@example.com",
            owner_name="Alice", ownership_score=0.9, commits_count=20, lines_changed=400,
            last_commit_date=now - timedelta(days=1),
        ),
        CodeOwnership(
            repository_id=repo_id, file_path="app/service.py", owner_email="bob@example.com",
            owner_name="Bob", ownership_score=0.7, commits_count=12, lines_changed=200,
            last_commit_date=now - timedelta(days=10),
        ),
    ])
    await db_session.flush()

    summary = await analyzer.get_ownership_summary(repo_id, db_session)
    assert summary.repository_id == repo_id
    assert summary.total_files == 5
    assert summary.files_with_ownership == 2
    assert summary.files_unowned == 3
    assert summary.unique_owners == 2
    assert summary.ownership_coverage == 40.0
    assert len(summary.top_contributors) == 2


@pytest.mark.asyncio
async def test_identify_unowned_files(db_session, repo_id, analyzer, files_on_disk):
    now = datetime.now(timezone.utc)
    db_session.add(CodeOwnership(
        repository_id=repo_id, file_path="app/core.py", owner_email="alice@example.com",
        owner_name="Alice", ownership_score=0.8, commits_count=10, lines_changed=200,
        last_commit_date=now - timedelta(days=3),
    ))
    await db_session.flush()

    unowned = await analyzer.identify_unowned_files(repo_id, db_session)
    assert "app/core.py" not in unowned
    assert "app/service.py" in unowned
    assert "app/auth.py" in unowned
    assert "tests/test_core.py" in unowned
    assert "docs/README.md" in unowned


@pytest.mark.asyncio
async def test_match_codeowners_to_files(analyzer):
    rules = analyzer.parse_codeowners(uuid.uuid4(), "*.py @alice\napp/auth.py @bob\ndocs/** @charlie")
    paths = ["app/core.py", "app/auth.py", "docs/README.md", "docs/guide/setup.md", "tests/test_main.py"]
    result = analyzer.match_codeowners_to_files(rules, paths)

    assert "alice" in result["app/core.py"]
    assert "bob" in result["app/auth.py"]
    assert "charlie" in result["docs/README.md"]
    assert "charlie" in result["docs/guide/setup.md"]
    assert "alice" in result["tests/test_main.py"]


def test_parse_maintainers_format(analyzer, repo_id):
    content = "# Maintainrs\nAlice <alice@example.com>\nBob <bob@example.com>\ncharlie@example.com\n"
    rules = analyzer.parse_codeowners(repo_id, content, "MAINTAINERS")
    assert len(rules) == 1
    assert rules[0].pattern == "*"
    assert len(rules[0].owners) == 3


def test_parse_maintainers_with_comments(analyzer, repo_id):
    content = "# comment\n\nalice@example.com\n# another\nbob@example.com\n"
    rules = analyzer.parse_codeowners(repo_id, content, "MAINTAINERS")
    assert len(rules) == 1
    assert len(rules[0].owners) == 2
