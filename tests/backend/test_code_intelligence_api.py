"""Code Intelligence API integration tests.

Uses the root conftest app/client fixtures. Tests all route groups through
the full FastAPI application with real DB and mocked downstream services.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, async_engine, async_session
from app.api.code_intelligence_api import (
    router,
    _get_current_user,
)
from app.core.database import get_db
from app.code_intelligence.models import (
    CodeIndex, CodeIndexVersion, CodeFile, CodeSymbol, CodeReference,
    CodeCall, CodeImport, CodeMetrics, CodeSmell, CodeChunk,
    IndexStatus, FileStatus, SymbolType, ReferenceType, Severity, SmellType,
)


pytestmark = pytest.mark.asyncio


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _create_test_data(db: AsyncSession, user):
    """Insert a repo, index, file, symbols, and return IDs."""
    repo_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    from app.models.repository import Repository
    repo = Repository(
        id=repo_id,
        name="test-repo",
        full_name="test/test-repo",
        git_url="https://github.com/test/repo",
        organization_id=None,
    )
    db.add(repo)

    idx_id = uuid.uuid4()
    idx = CodeIndex(
        id=idx_id,
        repository_id=repo_id,
        status=IndexStatus.READY,
        commit_sha="abc123",
        files_total=3,
        files_processed=3,
        symbols_extracted=6,
        chunks_created=1,
    )
    db.add(idx)

    version_id = uuid.uuid4()
    version = CodeIndexVersion(
        id=version_id,
        index_id=idx_id,
        version_number=1,
        is_active=True,
        commit_sha="abc123def",
    )
    db.add(version)

    file_id = uuid.uuid4()
    f = CodeFile(
        id=file_id,
        index_id=idx_id,
        repository_id=repo_id,
        file_path="src/main.py",
        file_name="main.py",
        language="python",
        size_bytes=1024,
        line_count=80,
        symbol_count=3,
        status=FileStatus.PARSED,
        indexed_at=now,
    )
    db.add(f)

    file_id2 = uuid.uuid4()
    f2 = CodeFile(
        id=file_id2,
        index_id=idx_id,
        repository_id=repo_id,
        file_path="src/utils.py",
        file_name="utils.py",
        language="python",
        size_bytes=512,
        line_count=30,
        symbol_count=2,
        status=FileStatus.PARSED,
        indexed_at=now,
    )
    db.add(f2)

    sym_id = uuid.uuid4()
    sym = CodeSymbol(
        id=sym_id,
        repository_id=repo_id,
        index_id=idx_id,
        file_id=file_id,
        symbol_id=str(sym_id),
        name="process_data",
        symbol_type=SymbolType.FUNCTION,
        qualified_name="src.main.process_data",
        start_line=10,
        end_line=40,
        signature="def process_data(items: list) -> dict",
    )
    db.add(sym)

    sym2_id = uuid.uuid4()
    sym2 = CodeSymbol(
        id=sym2_id,
        repository_id=repo_id,
        index_id=idx_id,
        file_id=file_id,
        symbol_id=str(sym2_id),
        name="validate_input",
        symbol_type=SymbolType.FUNCTION,
        qualified_name="src.main.validate_input",
        start_line=1,
        end_line=8,
        signature="def validate_input(data: dict) -> bool",
    )
    db.add(sym2)

    sym3_id = uuid.uuid4()
    sym3 = CodeSymbol(
        id=sym3_id,
        repository_id=repo_id,
        index_id=idx_id,
        file_id=file_id2,
        symbol_id=str(sym3_id),
        name="format_output",
        symbol_type=SymbolType.FUNCTION,
        qualified_name="src.utils.format_output",
        start_line=5,
        end_line=20,
        signature="def format_output(result: dict) -> str",
    )
    db.add(sym3)

    call_id = uuid.uuid4()
    call = CodeCall(
        id=call_id,
        repository_id=repo_id,
        index_id=idx_id,
        caller_symbol_id=sym_id,
        callee_symbol_id=sym3_id,
        caller_file_id=file_id,
        callee_name="format_output",
        call_line=25,
        call_type="direct",
        resolved=True,
        confidence=0.95,
    )
    db.add(call)

    ref_id = uuid.uuid4()
    ref = CodeReference(
        id=ref_id,
        repository_id=repo_id,
        index_id=idx_id,
        source_file_id=file_id,
        source_symbol_id=sym_id,
        target_symbol_id=sym3_id,
        reference_type=ReferenceType.IMPORT,
        source_line=1,
    )
    db.add(ref)

    imp_id = uuid.uuid4()
    imp = CodeImport(
        id=imp_id,
        repository_id=repo_id,
        index_id=idx_id,
        source_file_id=file_id,
        imported_name="format_output",
        import_type="from",
        is_external=False,
    )
    db.add(imp)

    metric_id = uuid.uuid4()
    metric = CodeMetrics(
        id=metric_id,
        file_id=file_id,
        repository_id=repo_id,
        loc=80,
        code_lines=60,
        comment_lines=10,
        blank_lines=10,
        cyclomatic_complexity=5,
        maintainability_index=75.0,
        calculated_at=now,
    )
    db.add(metric)

    smell_id = uuid.uuid4()
    smell = CodeSmell(
        id=smell_id,
        file_id=file_id,
        repository_id=repo_id,
        smell_type=SmellType.LONG_FUNCTION,
        severity=Severity.WARNING,
        message="Function process_data is too long (30 lines)",
        start_line=10,
        end_line=40,
        suggested_fix="Break into smaller functions",
        file_path="src/main.py",
    )
    db.add(smell)

    chunk_id = uuid.uuid4()
    chunk = CodeChunk(
        id=chunk_id,
        file_id=file_id,
        index_id=idx_id,
        repository_id=repo_id,
        chunk_type="function",
        content="def process_data(items):\n    validated = validate_input(items)\n    result = format_output(validated)\n    return result",
        start_line=10,
        end_line=40,
    )
    db.add(chunk)

    await db.commit()

    return {
        "repo_id": repo_id,
        "idx_id": idx_id,
        "version_id": version_id,
        "file_id": file_id,
        "file_id2": file_id2,
        "sym_id": sym_id,
        "sym2_id": sym2_id,
        "sym3_id": sym3_id,
    }


# ─── Auth Helper ────────────────────────────────────────────────────────────

class _AuthClient:
    def __init__(self, ac: AsyncClient, token: str):
        self._ac = ac
        self._token = token

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def get(self, url: str, **kwargs):
        return await self._ac.get(url, headers=self._headers(), **kwargs)

    async def post(self, url: str, **kwargs):
        return await self._ac.post(url, headers=self._headers(), **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self._ac.delete(url, headers=self._headers(), **kwargs)


@pytest_asyncio.fixture
async def ci_client(client: AsyncClient):
    """Authenticated client with test data in DB."""
    payload = {
        "email": "cicode_intelligence_test@novaforge.ai",
        "username": "cicode_intelligence_test",
        "password": "TestPass123!",
        "full_name": "CI Test User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    if resp.status_code == 201:
        token = resp.json().get("access_token", "")
    else:
        token = ""

    auth = _AuthClient(client, token)

    from app.api.auth import _get_current_user as real_get_current_user
    from app.core.database import get_db as real_get_db

    app_instance = client._transport.app
    override_user = app_instance.dependency_overrides.get(real_get_current_user)

    async def _mock_user():
        from app.models.user import User
        from app.core.database import async_session
        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            return result.scalar_one_or_none()

    if override_user is None:
        app_instance.dependency_overrides[real_get_current_user] = _mock_user

    async with AsyncClient(transport=client._transport, base_url=client.base_url) as ac:
        authed = _AuthClient(ac, token)
        yield authed

    app_instance.dependency_overrides.pop(real_get_current_user, None)


# ─── Index Management ──────────────────────────────────────────────────────

class TestIndexManagement:
    async def test_get_index(self, ci_client: _AuthClient, client: AsyncClient):
        from app.api.auth import _get_current_user
        from app.core.database import async_session
        from app.models.user import User
        from app.models.repository import Repository

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/index")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(data["idx_id"])
        assert body["status"] == IndexStatus.READY
        assert body["branch"] == "main"
        assert body["file_count"] == 3
        assert body["symbol_count"] == 6

    async def test_list_index_versions(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/index/versions")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        assert body[0]["commit_sha"] == "abc123def"

    async def test_delete_index(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.delete(f"/api/v1/code-intelligence/{data['repo_id']}/index")
        assert resp.status_code == 204

    async def test_get_index_not_found(self, ci_client: _AuthClient):
        resp = await ci_client.get(f"/api/v1/code-intelligence/{uuid.uuid4()}/index")
        assert resp.status_code == 404

    async def test_diff_index_versions(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        base_v = data["version_id"]
        target_v = uuid.uuid4()
        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/index/diff",
            json={"base_version_id": str(base_v), "target_version_id": str(target_v)},
        )
        assert resp.status_code in (200, 404)


# ─── File Intelligence ─────────────────────────────────────────────────────

class TestFileIntelligence:
    async def test_list_files(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/files")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2
        paths = {f["path"] for f in body}
        assert "src/main.py" in paths
        assert "src/utils.py" in paths

    async def test_list_files_by_language(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/files",
            params={"language": "python"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_file_content(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/files/{data['file_id']}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "file" in body
        assert "symbols" in body
        assert "references" in body
        assert "imports" in body
        assert body["file"]["path"] == "src/main.py"

    async def test_get_file_metrics(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/files/{data['file_id']}/metrics",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "src/main.py"
        assert body["cyclomatic_complexity"] == 5
        assert body["maintainability_index"] == 75.0

    async def test_get_files_by_language(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/files/by-language",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "python" in body
        assert body["python"] == 2


# ─── Symbol Intelligence ───────────────────────────────────────────────────

class TestSymbolIntelligence:
    async def test_list_symbols(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/symbols")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 3
        names = {s["name"] for s in body}
        assert "process_data" in names

    async def test_list_symbols_by_type(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/symbols",
            params={"symbol_type": SymbolType.FUNCTION.value},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_get_symbol_detail(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/symbols/{data['sym_id']}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "process_data"
        assert body["symbol_type"] == SymbolType.FUNCTION
        assert body["signature"] == "def process_data(items: list) -> dict"
        assert "calls" in body
        assert "called_by" in body

    async def test_get_symbol_call_graph(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/symbols/{data['sym_id']}/calls",
            params={"depth": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "calls" in body
        assert "total_edges" in body
        assert "symbol_id" in body
        assert body["symbol_id"] == str(data["sym_id"])

    async def test_get_symbol_dependencies(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/symbols/{data['sym_id']}/dependencies",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "direct_upstreams" in body
        assert "total_dependencies" in body


# ─── Graph Intelligence ────────────────────────────────────────────────────

class TestGraphIntelligence:
    async def test_get_repository_graph(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/graph")
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert "stats" in body
        assert body["stats"]["node_count"] == 3
        assert body["stats"]["edge_count"] == 1

    async def test_traverse_graph(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/graph/traverse",
            json={
                "symbol_id": str(data["sym_id"]),
                "direction": "outgoing",
                "max_depth": 3,
                "edge_types": [],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body

    async def test_get_module_graph(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/graph/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        modules = {m["module"] for m in body}
        assert "src" in modules

    async def test_detect_cycles(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/graph/cycles")
        assert resp.status_code == 200
        body = resp.json()
        assert "cycles" in body
        assert "total_cycles" in body
        assert body["total_cycles"] == 0


# ─── Code Quality ──────────────────────────────────────────────────────────

class TestCodeQuality:
    async def test_get_repository_metrics(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/quality/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["cyclomatic_complexity"] == 5

    async def test_get_quality_summary(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/quality/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_files"] == 1
        assert body["total_code_lines"] == 60
        assert body["total_smells"] >= 1

    async def test_scan_code_smells(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/quality/smells",
            json={"file_paths": [], "smell_types": [], "min_severity": "info"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_smells" in body
        assert "by_severity" in body
        assert "by_type" in body


# ─── Security ──────────────────────────────────────────────────────────────

class TestSecurityEndpoints:
    async def test_scan_security(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/security/scan",
            json={"file_paths": [], "vulnerability_types": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_vulnerabilities" in body
        assert "vulnerabilities" in body

    async def test_scan_secrets(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/security/secrets",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_secrets" in body
        assert "secrets" in body


# ─── Architecture ──────────────────────────────────────────────────────────

class TestArchitectureEndpoints:
    async def test_get_architecture_overview(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/architecture/overview",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "layers" in body
        assert "modules" in body

    async def test_get_architecture_dependencies(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(
            f"/api/v1/code-intelligence/{data['repo_id']}/architecture/dependencies",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert "circular_dependencies" in body


# ─── Impact Analysis ───────────────────────────────────────────────────────

class TestImpactAnalysisEndpoints:
    async def test_analyze_impact_symbol(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/impact/analyze",
            json={"symbol_id": str(data["sym_id"]), "change_type": "modify"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "affected_files" in body
        assert "impact_score" in body
        assert "risk_level" in body

    async def test_analyze_impact_no_target(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/impact/analyze",
            json={"change_type": "modify"},
        )
        assert resp.status_code == 400

    async def test_get_downstream_impact(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/impact/downstream",
            json={"symbol_id": str(data["sym_id"]), "max_depth": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "direct_dependencies" in body
        assert "total_affected" in body

    async def test_find_unused_code(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/impact/unused",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)


# ─── Search ────────────────────────────────────────────────────────────────

class TestSearchEndpoints:
    async def test_search_code(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/search",
            json={"query": "process_data", "max_results": 20, "include_context": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "process_data"
        assert "results" in body
        assert "total_results" in body

    async def test_search_symbols(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/search/symbols",
            json={"name": "process", "symbol_types": [], "fuzzy": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "total" in body
        assert body["total"] >= 1

    async def test_search_empty_query_rejected(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/search",
            json={"query": "", "max_results": 10, "include_context": False},
        )
        assert resp.status_code == 422


# ─── RAG Context ───────────────────────────────────────────────────────────

class TestRAGContextEndpoint:
    async def test_get_rag_context(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/rag/context",
            json={
                "query": "How does process_data work?",
                "max_tokens": 4096,
                "include_graph": True,
                "include_metrics": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "How does process_data work?"
        assert "context_chunks" in body
        assert "relevant_symbols" in body
        assert "total_tokens_estimate" in body


# ─── Index Health ──────────────────────────────────────────────────────────

class TestIndexHealthEndpoints:
    async def test_get_index_health(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.get(f"/api/v1/code-intelligence/{data['repo_id']}/index/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "index_id" in body
        assert "status" in body
        assert "health_score" in body
        assert "issues" in body
        assert "file_count" in body
        assert body["file_count"] == 2
        assert body["symbol_count"] == 3
        assert body["chunk_count"] == 1
        assert isinstance(body["health_score"], float)
        assert 0 <= body["health_score"] <= 100

    async def test_repair_index(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/index/repair",
            json={"repair_types": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "repairs_performed" in body
        assert "issues_fixed" in body
        assert "issues_remaining" in body


# ─── Validation ────────────────────────────────────────────────────────────

class TestInputValidation:
    async def test_search_query_too_long(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/search",
            json={"query": "x" * 501, "max_results": 10, "include_context": False},
        )
        assert resp.status_code == 422

    async def test_search_max_results_out_of_range(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/search",
            json={"query": "test", "max_results": 200, "include_context": False},
        )
        assert resp.status_code == 422

    async def test_traverse_depth_out_of_range(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/graph/traverse",
            json={
                "symbol_id": str(data["sym_id"]),
                "direction": "both",
                "max_depth": 100,
                "edge_types": [],
            },
        )
        assert resp.status_code == 422

    async def test_rag_context_max_tokens_out_of_range(self, ci_client: _AuthClient):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            data = await _create_test_data(db, user)

        resp = await ci_client.post(
            f"/api/v1/code-intelligence/{data['repo_id']}/rag/context",
            json={"query": "test", "max_tokens": 100000, "include_graph": True, "include_metrics": False},
        )
        assert resp.status_code == 422
