import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TESTING", "true")

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

from app.core.database import Base
from app.code_intelligence.models import CodeFile, CodeIndex, FileStatus, IndexStatus
from app.code_intelligence.configuration import ConfigurationAnalyzer


def _make_file(repo_id, idx_id, path, name, content, lang=None, is_config=False):
    return CodeFile(
        index_id=idx_id, repository_id=repo_id, file_path=path, file_name=name,
        language=lang, status=FileStatus.PARSED.value, is_config_file=is_config,
        content=content, file_hash="h", size_bytes=len(content), line_count=content.count("\n") + 1,
    )


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_mappers()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    expire_on_commit=False
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def repo_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def seeded(db_session, repo_id):
    idx_id = uuid.uuid4()
    files = [
        _make_file(repo_id, idx_id, "package.json", "package.json",
                   '{"name":"app","dependencies":{"react":"^18.0.0","react-dom":"^18.0.0"},"devDependencies":{"jest":"^29"}}',
                   lang="json", is_config=True),
        _make_file(repo_id, idx_id, "Dockerfile", "Dockerfile",
                   "FROM python:3.11\nEXPOSE 8080\nCMD [\"python\",\"app.py\"]",
                   lang="dockerfile", is_config=True),
        _make_file(repo_id, idx_id, ".env", ".env",
                   'API_KEY = "sk-1234567890abcdefghijklmnopqrstuv"\n', lang="dotenv", is_config=True),
        _make_file(repo_id, idx_id, "k8s/deploy.yaml", "deploy.yaml",
                   "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  replicas: 3\n",
                   lang="yaml", is_config=True),
    ]
    for f in files:
        db_session.add(f)
    await db_session.flush()
    return files


@pytest.mark.asyncio
async def test_parse_package_json(db_session, seeded):
    pkg = next(f for f in seeded if f.file_name == "package.json")
    analyzer = ConfigurationAnalyzer(db_session)
    info = await analyzer.parse_manifest(pkg.id)
    assert info is not None
    assert info.manifest_type == "package.json"
    assert "react" in info.dependencies and "jest" in info.dev_dependencies


@pytest.mark.asyncio
async def test_parse_dockerfile(db_session, seeded):
    d = next(f for f in seeded if f.file_name == "Dockerfile")
    analyzer = ConfigurationAnalyzer(db_session)
    info = await analyzer.parse_dockerfile(d.id)
    assert info is not None
    assert info.base_image == "python:3.11"
    assert any("8080" in p for p in info.exposed_ports)


@pytest.mark.asyncio
async def test_parse_kubernetes(db_session, seeded):
    k = next(f for f in seeded if f.file_name == "deploy.yaml")
    analyzer = ConfigurationAnalyzer(db_session)
    infos = await analyzer.parse_kubernetes_yaml(k.id)
    assert len(infos) == 1
    assert infos[0].kind == "Deployment"
    assert infos[0].name == "web"


@pytest.mark.asyncio
async def test_detect_secrets(db_session, seeded):
    analyzer = ConfigurationAnalyzer(db_session)
    findings = await analyzer.detect_secrets(seeded[0].repository_id)
    assert len(findings) >= 1
    assert findings[0].file_path == ".env"


@pytest.mark.asyncio
async def test_get_dependency_summary(db_session, seeded, repo_id):
    analyzer = ConfigurationAnalyzer(db_session)
    summary = await analyzer.get_dependency_summary(repo_id)
    assert summary.total >= 2
    assert "package.json" in summary.by_ecosystem


@pytest.mark.asyncio
async def test_get_framework_detection(db_session, seeded, repo_id):
    analyzer = ConfigurationAnalyzer(db_session)
    frameworks = await analyzer.get_framework_detection(repo_id)
    assert len(frameworks) >= 1
    names = {f.name for f in frameworks}
    assert "react" in names
