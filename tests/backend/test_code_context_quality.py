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
from app.code_intelligence.context_quality import (
    ContextChunkInfo,
    ContextQualityTracker,
)


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


def _chunk(cid, content, citation="", score=0.9):
    return ContextChunkInfo(
        chunk_id=cid, content=content, file_path="app/mod.py", symbol_name="foo",
        token_count=len(content), source_citation=citation, retrieval_score=score,
    )


@pytest.mark.asyncio
async def test_log_query_quality(db_session, repo_id):
    tracker = ContextQualityTracker(db_session)
    chunks = [_chunk("c1", "def foo(): pass"), _chunk("c2", "class Bar: pass")]
    metrics = await tracker.log_query_quality("how does foo work", [], chunks, str(repo_id))
    assert metrics is not None
    assert 0.0 <= metrics.overall_score <= 1.0


@pytest.mark.asyncio
async def test_detect_duplicates(db_session, repo_id):
    tracker = ContextQualityTracker(db_session)
    chunks = [_chunk("c1", "same content"), _chunk("c2", "same content")]
    groups = await tracker.detect_duplicate_context(chunks)
    assert len(groups) >= 1


@pytest.mark.asyncio
async def test_citation_coverage(db_session, repo_id):
    tracker = ContextQualityTracker(db_session)
    chunks = [_chunk("c1", "x", citation="app/mod.py:10"), _chunk("c2", "y", citation="")]
    cov = await tracker.check_citation_coverage(chunks)
    assert 0.0 <= cov.coverage_ratio <= 1.0
    assert cov.cited_chunks == 1


@pytest.mark.asyncio
async def test_token_utilization(db_session, repo_id):
    tracker = ContextQualityTracker(db_session)
    chunks = [_chunk("c1", "a" * 100), _chunk("c2", "b" * 100)]
    util = await tracker.measure_token_utilization(chunks, max_tokens=1000)
    assert util.total_tokens > 0
    assert 0.0 <= util.utilization_ratio <= 1.0


@pytest.mark.asyncio
async def test_aggregate_stats(db_session, repo_id):
    tracker = ContextQualityTracker(db_session)
    chunks = [_chunk("c1", "def foo(): pass")]
    await tracker.log_query_quality("q", [], chunks, str(repo_id))
    stats = await tracker.get_aggregate_stats(str(repo_id))
    assert stats is not None
    assert stats.total_queries >= 1
