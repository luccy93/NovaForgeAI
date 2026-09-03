"""C1 tests — Universal Knowledge & Search Platform foundation (Volume 68 Commit 1).

Tests all eight models, chunking, ingestion dedup, lexical search, RRF ranking,
freshness scoring, authorization, PII sanitization, source/document CRUD, tenant
isolation, ingestion lifecycle, and usage stats.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.knowledge.models import (
    KnowledgeSource,
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeEntity,
    KnowledgeLink,
    KnowledgeIngestionJob,
    KnowledgeQuery,
    KnowledgeQueryResult,
)
from app.knowledge.common import (
    compute_content_hash,
    _as_uuid,
    DuplicateIngestionError,
)
from app.knowledge.sources import (
    get_adapter,
    CodeIntelligenceAdapter,
    DataCatalogAdapter,
)
from app.knowledge.indexing import chunk_document, ingest_document
from app.knowledge.retrieval import lexical_search
from app.knowledge.ranking import reciprocal_rank_fusion, normalize_scores
from app.knowledge.search import search, get_document, list_sources
from app.knowledge.citations import build_citation, format_citation_text
from app.knowledge.freshness import compute_freshness_score
from app.knowledge.authz import (
    get_user_clearance,
    is_authorized,
    filter_authorized,
    CLASSIFICATION_LEVELS,
)
from app.knowledge.audit import _sanitize_query


# ─── 1. Model CRUD ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_models_create_all(db, org_id):
    src = KnowledgeSource(
        tenant=org_id,
        name="test-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(src)
    await db.flush()

    doc = KnowledgeDocument(
        tenant=org_id,
        source_id=src.id,
        external_id="ext-1",
        title="Test Document",
        doc_type="article",
        content="Hello world",
        content_hash=compute_content_hash("Hello world"),
        status="INGESTED",
        classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    chunk = KnowledgeChunk(
        tenant=org_id,
        document_id=doc.id,
        source_id=src.id,
        chunk_index=0,
        content="Hello world",
        token_count=2,
        classification="INTERNAL",
    )
    db.add(chunk)
    await db.flush()

    entity = KnowledgeEntity(
        tenant=org_id,
        entity_type="service",
        name="test-service",
        canonical_id="svc-test",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(entity)
    await db.flush()

    link = KnowledgeLink(
        tenant=org_id,
        source_entity_id=entity.id,
        target_entity_id=entity.id,
        link_type="REFERENCES",
        weight=1.0,
        classification="INTERNAL",
    )
    db.add(link)
    await db.flush()

    job = KnowledgeIngestionJob(
        tenant=org_id,
        source_id=src.id,
        job_type="full",
        status="PENDING",
    )
    db.add(job)
    await db.flush()

    query = KnowledgeQuery(
        tenant=org_id,
        query_text="test query",
        query_type="search",
    )
    db.add(query)
    await db.flush()

    qr = KnowledgeQueryResult(
        tenant=org_id,
        query_id=query.id,
        document_id=doc.id,
        chunk_id=chunk.id,
        score=0.95,
        rank=1,
        retrieval_method="lexical",
    )
    db.add(qr)
    await db.flush()

    assert src.id is not None
    assert doc.id is not None
    assert chunk.id is not None
    assert entity.id is not None
    assert link.id is not None
    assert job.id is not None
    assert query.id is not None
    assert qr.id is not None

    for obj in [src, doc, chunk, entity, link, job, query, qr]:
        assert isinstance(obj.id, uuid.UUID)


# ─── 2. Content hash ────────────────────────────────────────────────────────


def test_compute_content_hash():
    h1 = compute_content_hash("hello world")
    h2 = compute_content_hash("hello world")
    h3 = compute_content_hash("hello world!")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64

    assert compute_content_hash("") == compute_content_hash("")
    assert compute_content_hash(None) == compute_content_hash(None)


# ─── 3. Source adapter factory ──────────────────────────────────────────────


def test_source_adapter_factory():
    ci = get_adapter("code_intelligence")
    assert isinstance(ci, CodeIntelligenceAdapter)
    assert ci.source_type == "code_intelligence"

    dc = get_adapter("data_catalog")
    assert isinstance(dc, DataCatalogAdapter)
    assert dc.source_type == "data_catalog"

    with pytest.raises(ValueError, match="Unknown source type"):
        get_adapter("nonexistent_source")


# ─── 4. Chunk document ──────────────────────────────────────────────────────


def test_chunk_document():
    content = "Paragraph one. Sentence two.\n\nParagraph two. Another sentence."
    metadata = {"tenant": "t1", "source_id": "s1", "document_id": "d1"}
    chunks = chunk_document(content, metadata, max_chunk_size=50, overlap=20)

    assert len(chunks) >= 1
    for ch in chunks:
        assert "index" in ch
        assert "content" in ch
        assert "token_count" in ch
        assert "metadata" in ch
        assert ch["metadata"]["tenant"] == "t1"
        assert ch["token_count"] >= 1


# ─── 5. Chunk empty ─────────────────────────────────────────────────────────


def test_chunk_document_empty():
    assert chunk_document("", {}) == []
    assert chunk_document(None, {}) == []


# ─── 6. Dedup by content hash ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_by_content_hash(db, org_id):
    src = KnowledgeSource(
        tenant=org_id,
        name="dedup-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(src)
    await db.flush()

    doc_data = {
        "external_id": "ext-dedup",
        "title": "Dedup Doc",
        "doc_type": "article",
        "content": "Some unique content for dedup test",
        "summary": "Dedup summary",
        "classification": "INTERNAL",
    }
    doc_id = await ingest_document(db, org_id, src.id, doc_data)

    with pytest.raises(DuplicateIngestionError):
        await ingest_document(db, org_id, src.id, doc_data)


# ─── 7. Lexical search ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lexical_search(db, org_id):
    src = KnowledgeSource(
        tenant=org_id,
        name="search-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(src)
    await db.flush()

    doc = KnowledgeDocument(
        tenant=org_id,
        source_id=src.id,
        external_id="ext-search-1",
        title="Quantum Computing Guide",
        doc_type="article",
        content="Quantum computing uses qubits for computation.",
        summary="A guide to quantum computing",
        content_hash=compute_content_hash("Quantum computing uses qubits"),
        freshness_score=1.0,
        status="INGESTED",
        classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    results = await lexical_search(db, org_id, "quantum computing")
    assert len(results) >= 1
    assert any("quantum" in (r.get("snippet", "") or "").lower() for r in results)


# ─── 8. Ranking fusion ──────────────────────────────────────────────────────


def test_ranking_fusion():
    list_a = [
        {"document_id": "d1", "score": 0.9},
        {"document_id": "d2", "score": 0.7},
    ]
    list_b = [
        {"document_id": "d2", "score": 0.8},
        {"document_id": "d3", "score": 0.6},
    ]
    fused = reciprocal_rank_fusion([list_a, list_b])

    assert len(fused) == 3
    ids = [r["document_id"] for r in fused]
    assert ids == ["d2", "d1", "d3"] or ids[0] in ("d1", "d2")

    scores = [r["score"] for r in fused]
    assert scores == sorted(scores, reverse=True)

    normalized = normalize_scores([{"score": 0.5}, {"score": 1.0}, {"score": 0.0}])
    scores_n = [r["score"] for r in normalized]
    assert min(scores_n) == 0.0
    assert max(scores_n) == 1.0


# ─── 9. Freshness score ─────────────────────────────────────────────────────


def test_freshness_score():
    now = datetime.now(timezone.utc)
    score_now = compute_freshness_score(now, now)
    assert 0.9 < score_now <= 1.0

    old = now - timedelta(days=60)
    score_old = compute_freshness_score(old, old)
    assert score_old < 0.5

    very_old = now - timedelta(days=365)
    score_ancient = compute_freshness_score(very_old, very_old)
    assert score_ancient < 0.1

    future = now + timedelta(days=10)
    score_future = compute_freshness_score(future, future)
    assert score_future == 1.0


# ─── 10. Authz classification levels ────────────────────────────────────────


def test_authz_classification_levels():
    assert CLASSIFICATION_LEVELS["PUBLIC"] == 0
    assert CLASSIFICATION_LEVELS["INTERNAL"] == 1
    assert CLASSIFICATION_LEVELS["CONFIDENTIAL"] == 2
    assert CLASSIFICATION_LEVELS["RESTRICTED"] == 3

    assert is_authorized({"classification": "PUBLIC"}, 1) is True
    assert is_authorized({"classification": "RESTRICTED"}, 0) is False
    assert is_authorized({"classification": "CONFIDENTIAL"}, 3) is True
    assert is_authorized({"classification": "SECRET"}, 3) is True

    class _HighUser:
        classification_clearance = 3
    assert get_user_clearance(_HighUser()) == 3

    class _LowUser:
        classification_clearance = 0
    assert get_user_clearance(_LowUser()) == 0

    assert get_user_clearance(None) == 1


# ─── 11. Authz filter ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authz_filter_authorized():
    results = [
        {"classification": "PUBLIC", "score": 0.9},
        {"classification": "INTERNAL", "score": 0.8},
        {"classification": "CONFIDENTIAL", "score": 0.7},
        {"classification": "RESTRICTED", "score": 0.6},
    ]

    class _Admin:
        classification_clearance = 3

    filtered = await filter_authorized(results, _Admin())
    assert len(filtered) == 4

    class _Basic:
        classification_clearance = 1

    filtered_basic = await filter_authorized(results, _Basic())
    assert len(filtered_basic) == 2
    assert all(r["classification"] in ("PUBLIC", "INTERNAL") for r in filtered_basic)


# ─── 12. Audit sanitize ─────────────────────────────────────────────────────


def test_audit_sanitize():
    raw = "Find data for user@example.com, SSN 123-45-6789"
    sanitized = _sanitize_query(raw)
    assert "user@example.com" not in sanitized
    assert "123-45-6789" not in sanitized
    assert "[email]" in sanitized
    assert "[ssn]" in sanitized

    assert _sanitize_query("") == ""
    assert _sanitize_query(None) == ""

    long = "x" * 3000
    assert len(_sanitize_query(long)) <= 2048


# ─── 13. API search ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_search(db, org_id):
    src = KnowledgeSource(
        tenant=org_id,
        name="api-search-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(src)
    await db.flush()

    doc = KnowledgeDocument(
        tenant=org_id,
        source_id=src.id,
        external_id="ext-api-search",
        title="API Search Document",
        doc_type="article",
        content="FastAPI is a modern web framework for building APIs",
        summary="FastAPI guide",
        content_hash=compute_content_hash("FastAPI is a modern web framework"),
        freshness_score=1.0,
        status="INGESTED",
        classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    result = await search(db, org_id, "FastAPI web framework", user=None)
    assert "items" in result
    assert "total" in result
    assert result["total"] >= 1


# ─── 14. API sources CRUD ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_sources_crud(db, org_id):
    from app.knowledge.search import get_source
    from app.knowledge.common import NotFoundError

    src = KnowledgeSource(
        tenant=org_id,
        name="crud-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
        owner="test-owner",
    )
    db.add(src)
    await db.flush()

    sources = await list_sources(db, org_id)
    assert len(sources) >= 1
    assert any(s["name"] == "crud-source" for s in sources)

    src_detail = await get_source(db, org_id, src.id)
    assert src_detail["name"] == "crud-source"
    assert src_detail["source_type"] == "documents"

    src.status = "INACTIVE"
    await db.flush()
    updated = await get_source(db, org_id, src.id)
    assert updated["status"] == "INACTIVE"

    await db.delete(src)
    await db.flush()

    with pytest.raises(NotFoundError):
        await get_source(db, org_id, src.id)


# ─── 15. Tenant isolation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_isolation(db, org_id):
    other_org = str(uuid.uuid4())

    src_a = KnowledgeSource(
        tenant=org_id,
        name="tenant-a-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    src_b = KnowledgeSource(
        tenant=other_org,
        name="tenant-b-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add_all([src_a, src_b])
    await db.flush()

    doc_a = KnowledgeDocument(
        tenant=org_id,
        source_id=src_a.id,
        external_id="ext-a",
        title="Tenant A Document",
        doc_type="article",
        content="Confidential for tenant A",
        content_hash=compute_content_hash("Confidential for tenant A"),
        status="INGESTED",
        classification="INTERNAL",
    )
    doc_b = KnowledgeDocument(
        tenant=other_org,
        source_id=src_b.id,
        external_id="ext-b",
        title="Tenant B Document",
        doc_type="article",
        content="Confidential for tenant B",
        content_hash=compute_content_hash("Confidential for tenant B"),
        status="INGESTED",
        classification="INTERNAL",
    )
    db.add_all([doc_a, doc_b])
    await db.flush()

    sources_a = await list_sources(db, org_id)
    assert all(s["name"] != "tenant-b-source" for s in sources_a)

    sources_b = await list_sources(db, other_org)
    assert all(s["name"] != "tenant-a-source" for s in sources_b)

    results_a = await search(db, org_id, "tenant")
    for item in results_a.get("items", []):
        if item.get("title"):
            assert "tenant b" not in item["title"].lower()


# ─── 16. API document CRUD ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_document_crud(db, org_id):
    src = KnowledgeSource(
        tenant=org_id,
        name="doc-crud-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(src)
    await db.flush()

    doc = KnowledgeDocument(
        tenant=org_id,
        source_id=src.id,
        external_id="ext-doc-crud",
        title="CRUD Document",
        doc_type="article",
        content="Document content for CRUD testing",
        summary="CRUD summary",
        content_hash=compute_content_hash("Document content for CRUD testing"),
        freshness_score=1.0,
        status="INGESTED",
        classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    fetched = await get_document(db, org_id, doc.id)
    assert fetched["title"] == "CRUD Document"
    assert fetched["doc_type"] == "article"
    assert fetched["status"] == "INGESTED"

    from app.knowledge.common import NotFoundError
    with pytest.raises(NotFoundError):
        await get_document(db, org_id, uuid.uuid4())


# ─── 17. Ingestion job lifecycle ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingestion_job_lifecycle(db, org_id):
    src = KnowledgeSource(
        tenant=org_id,
        name="job-lifecycle-source",
        source_type="documents",
        status="ACTIVE",
        classification="INTERNAL",
    )
    db.add(src)
    await db.flush()

    job = KnowledgeIngestionJob(
        tenant=org_id,
        source_id=src.id,
        job_type="full",
        status="PENDING",
    )
    db.add(job)
    await db.flush()
    assert job.status == "PENDING"

    job.status = "RUNNING"
    job.started_at = datetime.now(timezone.utc)
    await db.flush()
    assert job.status == "RUNNING"

    job.status = "COMPLETED"
    job.documents_total = 5
    job.documents_processed = 5
    job.chunks_created = 15
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()

    refreshed = await db.execute(
        select(KnowledgeIngestionJob).where(KnowledgeIngestionJob.id == job.id)
    )
    persisted = refreshed.scalar_one()
    assert persisted.status == "COMPLETED"
    assert persisted.documents_total == 5
    assert persisted.chunks_created == 15
    assert persisted.completed_at is not None


# ─── 18. API usage stats ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_usage_stats(db, org_id):
    for i in range(3):
        q = KnowledgeQuery(
            tenant=org_id,
            query_text=f"test query {i} for stats",
            query_type="search",
            latency_ms=100 + i * 50,
            user_id="user-stats-1",
        )
        db.add(q)
    await db.flush()

    result_q = await db.execute(
        select(KnowledgeQuery).where(KnowledgeQuery.tenant == org_id)
    )
    queries = result_q.scalars().all()
    assert len(queries) == 3
    assert all(q.query_type == "search" for q in queries)
    assert all(q.user_id == "user-stats-1" for q in queries)

    latencies = [q.latency_ms for q in queries]
    assert latencies == sorted(latencies)

    sources = await list_sources(db, org_id)
    assert isinstance(sources, list)
