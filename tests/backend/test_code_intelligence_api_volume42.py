"""Volume 42 — new Code Intelligence API endpoint integration tests.

Tests the recently added endpoint groups (tests, ownership, history,
config, docs, summary, consistency, events, context-quality) through the
full FastAPI application.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, async_session
from app.api.code_intelligence_api import router, _get_current_user
from app.code_intelligence.models import (
    CodeIndex, CodeIndexVersion, CodeFile, CodeSymbol, CodeChunk,
    CodeOwnership, CodeHistory, CodeTest,
    IndexStatus, FileStatus, SymbolType,
)


pytestmark = pytest.mark.asyncio


async def _create_volume42_data(db: AsyncSession):
    repo_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    from app.models.repository import Repository

    repo = Repository(
        id=repo_id, name="v42-repo", full_name="test/v42-repo",
        git_url="https://github.com/test/v42", organization_id=None,
    )
    db.add(repo)

    idx_id = uuid.uuid4()
    idx = CodeIndex(
        id=idx_id, repository_id=repo_id, status=IndexStatus.READY,
        commit_sha="abc123", files_total=4, files_processed=4, symbols_extracted=2,
    )
    db.add(idx)

    version = CodeIndexVersion(
        id=uuid.uuid4(), index_id=idx_id, version_number=1,
        is_active=True, commit_sha="abc123def",
    )
    db.add(version)

    main_id = uuid.uuid4()
    main = CodeFile(
        id=main_id, index_id=idx_id, repository_id=repo_id,
        file_path="src/main.py", file_name="main.py", language="python",
        size_bytes=200, line_count=20, symbol_count=1, status=FileStatus.PARSED,
        content='def run():\n    """Run."""\n    return 1\n',
        is_test_file=False, indexed_at=now,
    )
    db.add(main)
    db.add(CodeChunk(
        repository_id=repo_id, index_id=idx_id, file_id=main_id,
        chunk_type="file_content", content='def run():\n    """Run."""\n    return 1\n',
        language="python", start_line=1, end_line=3, token_count=20,
    ))

    readme_id = uuid.uuid4()
    readme = CodeFile(
        id=readme_id, index_id=idx_id, repository_id=repo_id,
        file_path="README.md", file_name="README.md", language="markdown",
        size_bytes=50, line_count=5, status=FileStatus.PARSED,
        content="# V42\n\n## Install\npip install.\n", is_documentation=True, indexed_at=now,
    )
    db.add(readme)
    db.add(CodeChunk(
        repository_id=repo_id, index_id=idx_id, file_id=readme_id,
        chunk_type="file_content", content="# V42\n\n## Install\npip install.\n",
        language="markdown", start_line=1, end_line=5, token_count=10,
    ))

    test_id = uuid.uuid4()
    testf = CodeFile(
        id=test_id, index_id=idx_id, repository_id=repo_id,
        file_path="tests/test_main.py", file_name="test_main.py", language="python",
        size_bytes=60, line_count=4, status=FileStatus.PARSED,
        content="def test_run():\n    assert run() == 1\n", is_test_file=True, indexed_at=now,
    )
    db.add(testf)

    sym = CodeSymbol(
        id=uuid.uuid4(), repository_id=repo_id, index_id=idx_id, file_id=main_id,
        symbol_id=str(uuid.uuid4()), name="run", symbol_type=SymbolType.FUNCTION,
        qualified_name="src.main.run", language="python", start_line=1, end_line=2,
        docstring="Run.",
    )
    db.add(sym)

    db.add(CodeTest(
        repository_id=repo_id, file_id=test_id, test_type="unit",
        test_name="test_run", framework="pytest",
    ))

    for i, (email, days) in enumerate([("alice@x.com", 1), ("bob@x.com", 3)], 1):
        db.add(CodeOwnership(
            repository_id=repo_id, file_path="src/main.py", owner_email=email,
            owner_name=email.split("@")[0].title(), ownership_score=0.8,
            commits_count=10, lines_changed=200, last_commit_date=now - timedelta(days=days),
        ))
    for i in range(3):
        db.add(CodeHistory(
            repository_id=repo_id, file_id=main_id, file_path="src/main.py",
            commit_sha=f"sha{i}", author_email="alice@x.com", author_name="Alice",
            commit_date=now - timedelta(days=i), change_type="M",
            lines_added=10, lines_deleted=2,
        ))

    await db.flush()
    return repo_id


class _AuthClient:
    def __init__(self, ac: AsyncClient, token: str):
        self._ac = ac
        self._token = token

    def _h(self):
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def get(self, url, **kw):
        return await self._ac.get(url, headers=self._h(), **kw)


@pytest_asyncio.fixture
async def ci_client(client: AsyncClient):
    payload = {
        "email": "v42test@novaforge.ai", "username": "v42test",
        "password": "TestPass123!", "full_name": "V42 Test",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    token = resp.json().get("access_token", "") if resp.status_code == 201 else ""
    auth = _AuthClient(client, token)

    from app.api.auth import _get_current_user as real_get_current_user

    app_instance = client._transport.app

    async def _mock_user():
        from app.models.user import User
        async with async_session() as db:
            return (await db.execute(select(User).limit(1))).scalar_one_or_none()

    if app_instance.dependency_overrides.get(real_get_current_user) is None:
        app_instance.dependency_overrides[real_get_current_user] = _mock_user

    async with AsyncClient(transport=client._transport, base_url=client.base_url) as ac:
        yield _AuthClient(ac, token)

    app_instance.dependency_overrides.pop(real_get_current_user, None)


@pytest_asyncio.fixture
async def repo_id(client: AsyncClient):
    async with async_session() as db:
        rid = await _create_volume42_data(db)
        await db.commit()
    return rid


class TestVolume42Endpoints:
    async def test_tests(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/tests")
        assert r.status_code == 200

    async def test_tests_quality(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/tests/quality")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_tests_gaps(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/tests/gaps")
        assert r.status_code == 200

    async def test_ownership(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/ownership")
        assert r.status_code == 200

    async def test_ownership_contributors(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/ownership/contributors")
        assert r.status_code == 200

    async def test_ownership_bus_risk(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/ownership/bus-risk")
        assert r.status_code == 200

    async def test_history_hotspots(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/history/hotspots")
        assert r.status_code == 200

    async def test_history_churn(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/history/churn")
        assert r.status_code == 200

    async def test_history_authors(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/history/authors")
        assert r.status_code == 200

    async def test_history_summary(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/history/summary")
        assert r.status_code == 200

    async def test_config(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/config")
        assert r.status_code == 200

    async def test_config_dependencies(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/config/dependencies")
        assert r.status_code == 200

    async def test_docs(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/docs")
        assert r.status_code == 200

    async def test_summary(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/summary")
        assert r.status_code == 200

    async def test_summary_languages(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/summary/languages")
        assert r.status_code == 200

    async def test_summary_entry_points(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/summary/entry-points")
        assert r.status_code == 200

    async def test_consistency(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/consistency")
        assert r.status_code == 200

    async def test_consistency_issues(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/consistency/issues")
        assert r.status_code == 200

    async def test_events(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/events")
        assert r.status_code == 200

    async def test_context_quality(self, ci_client, repo_id):
        r = await ci_client.get(f"/api/v1/code-intelligence/{repo_id}/context-quality")
        assert r.status_code == 200
