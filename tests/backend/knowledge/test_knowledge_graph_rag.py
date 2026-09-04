"""C2 tests — Knowledge Graph, RAG, Security & Explainability (Volume 68 Commit 2).

Tests entity resolution, graph construction, traversal/pathfinding, RAG context
assembly, semantic caching, security hardening, admin lifecycle, and explainable
retrieval.
"""

import uuid
from datetime import datetime, timezone, timedelta

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
    KnowledgeCacheEntry,
    KnowledgeAdminAudit,
)
from app.knowledge.common import (
    compute_content_hash,
    _as_uuid,
)
from app.knowledge.graph import (
    resolve_entities,
    create_entity_links,
    get_entity_neighbors,
    merge_entities,
    get_graph_stats,
)
from app.knowledge.traversal import (
    traverse_graph,
    find_shortest_path,
    expand_neighborhood,
    rank_entities_by_centrality,
)
from app.knowledge.rag_builder import (
    build_rag_context,
    select_diverse_chunks,
    format_context_for_llm,
    score_relevance_to_query,
)
from app.knowledge.cache import (
    get_cached_result,
    store_in_cache,
    invalidate_cache,
    get_cache_stats,
    prune_expired_cache,
)
from app.knowledge.security import (
    validate_query_input,
    redact_pii,
    check_rate_limit,
    sanitize_connector_config,
    detect_sensitive_query,
)
from app.knowledge.admin import (
    get_source_health,
    bulk_update_source_status,
    get_system_stats,
    export_source_metadata,
)
from app.knowledge.explain import (
    explain_search_results,
    get_scoring_breakdown,
    get_source_lineage,
    format_explanation,
)


# ─── 1. Entity Resolution & Knowledge Graph ─────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_creates_and_deduplicates(db, org_id):
    doc = KnowledgeDocument(
        tenant=org_id,
        source_id=uuid.uuid4(),
        external_id="ext",
        title="Doc",
        doc_type="article",
        content="content",
        content_hash=compute_content_hash("content"),
        status="INGESTED",
        classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    raw = [
        {"name": "Auth Service", "entity_type": "service", "confidence": 0.9},
        {"name": "Auth Service", "entity_type": "service", "confidence": 0.7},
        {"name": "Payment Gateway", "entity_type": "integration", "confidence": 0.8},
    ]
    resolved = await resolve_entities(db, org_id, doc.id, raw)

    assert len(resolved) == 3
    new_ones = [r for r in resolved if r["is_new"]]
    # First Auth Service is new, second is merged, Payment Gateway is new
    assert len(new_ones) == 2

    # Verify dedup: exactly one Auth Service entity in DB
    stmt = select(KnowledgeEntity).where(
        KnowledgeEntity.tenant == org_id,
        KnowledgeEntity.name == "Auth Service",
    )
    entities = (await db.execute(stmt)).scalars().all()
    assert len(entities) == 1
    # Confidence boosted from merging
    assert entities[0].confidence >= 0.8
    # source_ids merged
    assert str(doc.id) in (entities[0].source_ids or [])


@pytest.mark.asyncio
async def test_create_entity_links_and_strengthen(db, org_id):
    e1 = KnowledgeEntity(tenant=org_id, entity_type="service", name="svc-a",
                         canonical_id="a", status="ACTIVE", classification="INTERNAL")
    e2 = KnowledgeEntity(tenant=org_id, entity_type="service", name="svc-b",
                         canonical_id="b", status="ACTIVE", classification="INTERNAL")
    db.add(e1)
    db.add(e2)
    await db.flush()

    pairs = [
        {
            "source_id": str(e1.id), "target_id": str(e2.id),
            "link_type": "DEPENDS_ON", "weight": 1.0,
            "classification": "INTERNAL",
        }
    ]
    created = await create_entity_links(db, org_id, uuid.uuid4(), pairs)
    assert len(created) == 1
    assert created[0]["is_new"] is True

    # Strengthen: same pair again should update not recreate
    await create_entity_links(db, org_id, uuid.uuid4(), pairs)
    stmt = select(KnowledgeLink).where(
        KnowledgeLink.tenant == org_id,
        KnowledgeLink.link_type == "DEPENDS_ON",
    )
    links = (await db.execute(stmt)).scalars().all()
    assert len(links) == 1
    assert links[0].weight > 1.0


@pytest.mark.asyncio
async def test_get_entity_neighbors(db, org_id):
    a = KnowledgeEntity(tenant=org_id, entity_type="service", name="a",
                        canonical_id="a", status="ACTIVE", classification="INTERNAL")
    b = KnowledgeEntity(tenant=org_id, entity_type="service", name="b",
                        canonical_id="b", status="ACTIVE", classification="INTERNAL")
    db.add(a)
    db.add(b)
    await db.flush()

    db.add(KnowledgeLink(tenant=org_id, source_entity_id=a.id, target_entity_id=b.id,
                         link_type="LINKS", weight=2.0, classification="INTERNAL"))
    await db.flush()

    result = await get_entity_neighbors(db, org_id, a.id, depth=1)
    assert result["entity"] is not None
    assert result["entity"]["id"] == str(a.id)
    assert len(result["neighbors"]) == 1
    assert result["neighbors"][0]["name"] == "b"
    assert len(result["links"]) == 1


@pytest.mark.asyncio
async def test_merge_entities_transfers_links(db, org_id):
    primary = KnowledgeEntity(tenant=org_id, entity_type="person", name="John Doe",
                              canonical_id="jd", status="ACTIVE", classification="INTERNAL")
    dup = KnowledgeEntity(tenant=org_id, entity_type="person", name="J. Doe",
                          canonical_id="jd2", status="ACTIVE", classification="INTERNAL")
    other = KnowledgeEntity(tenant=org_id, entity_type="person", name="Jane",
                            canonical_id="jn", status="ACTIVE", classification="INTERNAL")
    db.add_all([primary, dup, other])
    await db.flush()

    # Link from dup -> other
    db.add(KnowledgeLink(tenant=org_id, source_entity_id=dup.id, target_entity_id=other.id,
                         link_type="KNOWS", weight=1.0, classification="INTERNAL"))
    await db.flush()

    result = await merge_entities(db, org_id, primary.id, [dup.id])
    assert result["merged_count"] == 1
    assert result["links_transferred"] == 1

    # Dup soft-deleted
    stmt = select(KnowledgeEntity).where(KnowledgeEntity.id == dup.id)
    deleted = (await db.execute(stmt)).scalar_one()
    assert deleted.status == "DELETED"

    # Link now points to primary
    link_stmt = select(KnowledgeLink).where(
        KnowledgeLink.tenant == org_id, KnowledgeLink.link_type == "KNOWS"
    )
    link = (await db.execute(link_stmt)).scalar_one()
    assert str(link.source_entity_id) == str(primary.id)


@pytest.mark.asyncio
async def test_get_graph_stats(db, org_id):
    db.add_all([
        KnowledgeEntity(tenant=org_id, entity_type="service", name="x1",
                        canonical_id="x1", status="ACTIVE", confidence=0.9,
                        classification="INTERNAL"),
        KnowledgeEntity(tenant=org_id, entity_type="team", name="x2",
                        canonical_id="x2", status="ACTIVE", confidence=0.5,
                        classification="INTERNAL"),
    ])
    await db.flush()
    stats = await get_graph_stats(db, org_id)
    assert stats["entity_count"] == 2
    assert stats["entities_by_type"]["service"] == 1
    assert stats["entities_by_type"]["team"] == 1


# ─── 2. Graph Traversal ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_traverse_graph_multi_hop(db, org_id):
    a = KnowledgeEntity(tenant=org_id, entity_type="service", name="a",
                        canonical_id="a", status="ACTIVE", classification="INTERNAL")
    b = KnowledgeEntity(tenant=org_id, entity_type="service", name="b",
                        canonical_id="b", status="ACTIVE", classification="INTERNAL")
    c = KnowledgeEntity(tenant=org_id, entity_type="service", name="c",
                        canonical_id="c", status="ACTIVE", classification="INTERNAL")
    db.add_all([a, b, c])
    await db.flush()

    db.add_all([
        KnowledgeLink(tenant=org_id, source_entity_id=a.id, target_entity_id=b.id,
                      link_type="X", weight=1.0, classification="INTERNAL"),
        KnowledgeLink(tenant=org_id, source_entity_id=b.id, target_entity_id=c.id,
                      link_type="X", weight=1.0, classification="INTERNAL"),
    ])
    await db.flush()

    result = await traverse_graph(db, org_id, a.id, depth=2)
    assert len(result["nodes"]) == 3
    assert result["depth_reached"] == 2


@pytest.mark.asyncio
async def test_find_shortest_path(db, org_id):
    a = KnowledgeEntity(tenant=org_id, entity_type="svc", name="a",
                        canonical_id="a", status="ACTIVE", classification="INTERNAL")
    b = KnowledgeEntity(tenant=org_id, entity_type="svc", name="b",
                        canonical_id="b", status="ACTIVE", classification="INTERNAL")
    c = KnowledgeEntity(tenant=org_id, entity_type="svc", name="c",
                        canonical_id="c", status="ACTIVE", classification="INTERNAL")
    d = KnowledgeEntity(tenant=org_id, entity_type="svc", name="d",
                        canonical_id="d", status="ACTIVE", classification="INTERNAL")
    db.add_all([a, b, c, d])
    await db.flush()

    db.add_all([
        KnowledgeLink(tenant=org_id, source_entity_id=a.id, target_entity_id=b.id,
                      link_type="L", weight=1.0, classification="INTERNAL"),
        KnowledgeLink(tenant=org_id, source_entity_id=b.id, target_entity_id=c.id,
                      link_type="L", weight=1.0, classification="INTERNAL"),
        KnowledgeLink(tenant=org_id, source_entity_id=a.id, target_entity_id=d.id,
                      link_type="L", weight=1.0, classification="INTERNAL"),
        KnowledgeLink(tenant=org_id, source_entity_id=d.id, target_entity_id=c.id,
                      link_type="L", weight=1.0, classification="INTERNAL"),
    ])
    await db.flush()

    result = await find_shortest_path(db, org_id, a.id, c.id)
    assert result["distance"] == 2
    assert len(result["path"]) == 3
    assert result["path"][0]["id"] == str(a.id)
    assert result["path"][-1]["id"] == str(c.id)


@pytest.mark.asyncio
async def test_expand_neighborhood(db, org_id):
    a = KnowledgeEntity(tenant=org_id, entity_type="svc", name="a",
                        canonical_id="a", status="ACTIVE", classification="INTERNAL")
    b = KnowledgeEntity(tenant=org_id, entity_type="svc", name="b",
                        canonical_id="b", status="ACTIVE", classification="INTERNAL")
    db.add_all([a, b])
    await db.flush()
    db.add(KnowledgeLink(tenant=org_id, source_entity_id=a.id, target_entity_id=b.id,
                         link_type="L", weight=1.0, classification="INTERNAL"))
    await db.flush()

    result = await expand_neighborhood(db, org_id, [a.id], hops=1)
    assert result["seed_count"] == 1
    assert result["expanded_count"] == 1
    assert len(result["nodes"]) == 2


@pytest.mark.asyncio
async def test_rank_entities_by_centrality(db, org_id):
    a = KnowledgeEntity(tenant=org_id, entity_type="svc", name="a",
                        canonical_id="a", status="ACTIVE", confidence=0.5,
                        classification="INTERNAL")
    b = KnowledgeEntity(tenant=org_id, entity_type="svc", name="b",
                        canonical_id="b", status="ACTIVE", confidence=1.0,
                        classification="INTERNAL")
    db.add_all([a, b])
    await db.flush()
    # Give 'a' two links, 'b' one link
    db.add_all([
        KnowledgeLink(tenant=org_id, source_entity_id=a.id, target_entity_id=b.id,
                      link_type="L1", weight=1.0, classification="INTERNAL"),
        KnowledgeLink(tenant=org_id, source_entity_id=b.id, target_entity_id=a.id,
                      link_type="L2", weight=1.0, classification="INTERNAL"),
    ])
    await db.flush()

    ranked = await rank_entities_by_centrality(db, org_id, limit=10)
    assert len(ranked) == 2
    # a has degree 2 * conf 0.5 = 1.0; b has degree 2 * conf 1.0 = 2.0 -> b first
    assert ranked[0]["id"] == str(b.id)


# ─── 3. RAG Context Builder ──────────────────────────────────────────────────


def test_select_diverse_chunks():
    results = [
        {"document_id": "d1", "source_id": "s1", "score": 0.9},
        {"document_id": "d2", "source_id": "s2", "score": 0.8},
        {"document_id": "d2", "source_id": "s2", "score": 0.7},  # dup of d2
    ]
    selected = select_diverse_chunks(results, max_chunks=3, diversity_factor=1.0)
    assert len(selected) == 3
    # Diversity factor 1.0 penalizes duplicate doc d2
    assert selected[0]["document_id"] == "d1"


def test_format_context_for_llm():
    chunks = [
        {"content": "Hello", "title": "Doc A", "source_name": "code"},
        {"content": "World", "title": "Doc B"},
    ]
    text = format_context_for_llm(chunks, query="test")
    assert "Hello" in text
    assert "[code]" in text
    assert "test" in text


def test_format_context_empty():
    text = format_context_for_llm([], query="q")
    assert "No relevant context" in text


def test_score_relevance_to_query():
    chunk = {"content": "the auth service handles tokens"}
    assert score_relevance_to_query(chunk, "auth service") == 1.0
    assert score_relevance_to_query(chunk, "") == 0.0


@pytest.mark.asyncio
async def test_build_rag_context(db, org_id):
    src = KnowledgeSource(tenant=org_id, name="code-repo", source_type="code_intel",
                          status="ACTIVE", classification="INTERNAL")
    db.add(src)
    await db.flush()

    doc = KnowledgeDocument(
        tenant=org_id, source_id=src.id, external_id="ext", title="Auth Guide",
        doc_type="guide", content="auth content", content_hash=compute_content_hash("auth content"),
        version="1", status="INGESTED", classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    chunk = KnowledgeChunk(
        tenant=org_id, document_id=doc.id, source_id=src.id, chunk_index=0,
        content="The auth service authenticates users using tokens.",
        token_count=8, classification="INTERNAL",
    )
    db.add(chunk)
    await db.flush()

    search_results = [
        {
            "document_id": str(doc.id), "chunk_id": str(chunk.id), "source_id": str(src.id),
            "score": 0.9, "method": "hybrid",
            "content": "The auth service authenticates users using tokens.",
            "title": "Auth Guide",
        }
    ]

    ctx = await build_rag_context(db, org_id, "how does auth work?", search_results)
    assert len(ctx["chunks_used"]) >= 1
    assert ctx["total_tokens"] > 0
    assert len(ctx["citations"]) == 1
    assert ctx["citations"][0]["title"] == "Auth Guide"
    assert "auth" in ctx["context_text"]


# ─── 4. Semantic Cache ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_store_and_hit(db, org_id):
    key = await store_in_cache(db, org_id, "query one", [{"document_id": "d1", "score": 0.8}])
    assert key != ""

    cached = await get_cached_result(db, org_id, "query one")
    assert cached is not None
    assert cached["results"][0]["document_id"] == "d1"
    # Hit count increment
    cached2 = await get_cached_result(db, org_id, "query one")
    assert cached2["hit_count"] == 2


@pytest.mark.asyncio
async def test_cache_miss_and_invalidate(db, org_id):
    # Different query -> miss
    cached = await get_cached_result(db, org_id, "totally different")
    assert cached is None

    await store_in_cache(db, org_id, "relevant", [
        {"source_id": "src-123", "score": 0.5},
    ])

    invalidated = await invalidate_cache(db, org_id, source_id="src-123")
    assert invalidated >= 1
    assert await get_cached_result(db, org_id, "relevant") is None


@pytest.mark.asyncio
async def test_cache_stats(db, org_id):
    await store_in_cache(db, org_id, "q", [{"document_id": "d"}], ttl_hours=24)
    stats = await get_cache_stats(db, org_id)
    assert stats["total_entries"] == 1
    assert stats["active_entries"] == 1


# ─── 5. Security Hardening ───────────────────────────────────────────────────


def test_validate_query_input_sql_injection():
    result = validate_query_input("SELECT * FROM users; DROP TABLE x --")
    assert "sql_injection_suspected" in result["violations"]
    assert "--" not in result["cleaned_query"]


def test_validate_query_input_empty():
    result = validate_query_input("   ")
    assert result["valid"] is False


def test_validate_query_input_xss():
    result = validate_query_input("<script>alert('x')</script>")
    assert "xss_suspected" in result["violations"]


def test_redact_pii():
    text = "Contact dev@example.com or 123-45-6789 or 4111111111111111"
    redacted = redact_pii(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_SSN]" in redacted
    assert "[REDACTED_CARD]" in redacted
    assert "dev@example.com" not in redacted


def test_rate_limit():
    result = check_rate_limit("tenant", "user", "search", max_requests=3, window_seconds=60)
    assert result["allowed"] is True
    check_rate_limit("tenant", "user", "search", max_requests=3, window_seconds=60)
    check_rate_limit("tenant", "user", "search", max_requests=3, window_seconds=60)
    blocked = check_rate_limit("tenant", "user", "search", max_requests=3, window_seconds=60)
    assert blocked["allowed"] is False
    assert blocked["retry_after_seconds"] > 0


def test_sanitize_connector_config():
    config = {"url": "http://x", "password": "supersecret", "token": "abc"}
    sanitized = sanitize_connector_config(config, "code_intel")
    assert sanitized["url"] == "http://x"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"


def test_detect_sensitive_query():
    res = detect_sensitive_query("how do we store passwords")
    assert res["is_sensitive"] is True
    assert any("password" in r for r in res["reasons"])


# ─── 6. Admin & Source Lifecycle ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_source_health(db, org_id):
    src = KnowledgeSource(tenant=org_id, name="src", source_type="code_intel",
                          status="ACTIVE", classification="INTERNAL",
                          last_ingested_at=datetime.now(timezone.utc))
    db.add(src)
    await db.flush()

    health = await get_source_health(db, org_id, src.id)
    assert health["source_id"] == str(src.id)
    assert health["status"] == "ACTIVE"
    assert health["document_count"] == 0
    assert health["health_score"] > 0.0


@pytest.mark.asyncio
async def test_get_source_health_not_found(db, org_id):
    health = await get_source_health(db, org_id, uuid.uuid4())
    assert health["status"] == "not_found"


@pytest.mark.asyncio
async def test_bulk_update_source_status(db, org_id):
    s1 = KnowledgeSource(tenant=org_id, name="s1", source_type="code_intel",
                         status="ACTIVE", classification="INTERNAL")
    s2 = KnowledgeSource(tenant=org_id, name="s2", source_type="code_intel",
                         status="ACTIVE", classification="INTERNAL")
    db.add_all([s1, s2])
    await db.flush()

    result = await bulk_update_source_status(db, org_id, [s1.id, s2.id], "PAUSED")
    assert result["updated_count"] == 2
    assert result["failed_ids"] == []


@pytest.mark.asyncio
async def test_get_system_stats(db, org_id):
    s1 = KnowledgeSource(tenant=org_id, name="s1", source_type="code_intel",
                         status="ACTIVE", classification="INTERNAL")
    db.add(s1)
    await db.flush()
    db.add(KnowledgeDocument(tenant=org_id, source_id=s1.id, external_id="e",
                             title="t", doc_type="a", content="c",
                             content_hash="h", status="INGESTED", classification="INTERNAL"))
    await db.flush()

    stats = await get_system_stats(db, org_id)
    assert stats["sources"]["total"] == 1
    assert stats["documents"]["total"] == 1


# ─── 7. Explainable Retrieval ───────────────────────────────────────────────


def test_get_scoring_breakdown():
    result = {"score": 0.8, "method": "vector", "retrieval_method": "vector"}
    breakdown = get_scoring_breakdown(result)
    assert breakdown["retrieval_method"] == "vector"
    assert "components" in breakdown
    assert "semantic_similarity" in breakdown["components"]


def test_format_explanation_error():
    text = format_explanation({"error": "query_not_found"})
    assert "query_not_found" in text


def test_format_explanation_verbose():
    explanation = {
        "query_text": "how does auth work",
        "retrieval_methods_used": ["lexical", "vector"],
        "total_results": 1,
        "total_latency_ms": 50,
        "results_explanation": [
            {
                "rank": 1,
                "retrieval_method": "vector",
                "score": 0.9,
                "document_info": {"title": "Auth Guide"},
                "scoring_breakdown": {"retrieval_method": "vector", "components": {"semantic_similarity": 0.63}},
            }
        ],
    }
    text = format_explanation(explanation, verbose=True)
    assert "Auth Guide" in text
    assert "semantic_similarity" in text


@pytest.mark.asyncio
async def test_get_source_lineage(db, org_id):
    src = KnowledgeSource(tenant=org_id, name="src", source_type="code_intel",
                          status="ACTIVE", classification="INTERNAL")
    db.add(src)
    await db.flush()

    doc = KnowledgeDocument(
        tenant=org_id, source_id=src.id, external_id="ext", title="Doc",
        doc_type="guide", content="content", content_hash="hash-val",
        status="INGESTED", classification="INTERNAL",
    )
    db.add(doc)
    await db.flush()

    lineage = await get_source_lineage(db, org_id, doc.id)
    assert lineage["document"]["title"] == "Doc"
    assert lineage["source"]["name"] == "src"