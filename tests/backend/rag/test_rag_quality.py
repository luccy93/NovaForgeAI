"""Volume 43 — RAG quality tests: IR metrics + citation accuracy."""

import math
import uuid

import pytest
from sqlalchemy import select

from app.rag.ingestion import Indexer, KnowledgeSourceRegistry
from app.rag.models import RagChunk
from app.rag.retrieval.service import RAGService


def _recall_at_k(retrieved_ids, relevant_ids, k):
    retrieved = retrieved_ids[:k]
    if not relevant_ids:
        return 0.0
    return len(set(retrieved) & set(relevant_ids)) / len(set(relevant_ids))


def _precision_at_k(retrieved_ids, relevant_ids, k):
    if k == 0:
        return 0.0
    return len(set(retrieved_ids[:k]) & set(relevant_ids)) / k


def _mrr(retrieved_ids, relevant_ids):
    for i, r in enumerate(retrieved_ids, start=1):
        if r in set(relevant_ids):
            return 1.0 / i
    return 0.0


def _ndcg(retrieved_ids, relevant_ids, k):
    def dcg(ids):
        return sum(1.0 / math.log2(i + 2) for i, _ in enumerate(ids) if ids[i] in set(relevant_ids))

    ideal = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal))
    denom = idcg or 1.0
    return dcg(retrieved_ids[:k]) / denom


def test_ir_metrics_known_values():
    retrieved = ["A", "B", "C"]
    relevant = {"A", "C"}
    k = 3
    assert _recall_at_k(retrieved, relevant, k) == 1.0
    assert abs(_precision_at_k(retrieved, relevant, k) - 2 / 3) < 1e-9
    assert _mrr(retrieved, relevant) == 1.0
    assert 0.9 < _ndcg(retrieved, relevant, k) <= 1.0


@pytest.mark.asyncio
async def test_end_to_end_recall(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    reg = KnowledgeSourceRegistry()
    src = await reg.create_source(db, tenant_id=tid, organization_id=oid, name="s", source_type="documentation")
    await db.commit()
    await Indexer(embedding_client=fake_embedding, vector_store=None).index_source(
        db, src.id, content="RECALLDOC_gamma_3322 the fox jumps"
    )
    await db.commit()
    chunk_id = str((await db.execute(select(RagChunk).where(RagChunk.source_id == src.id))).scalars().first().id)
    svc = RAGService(embedding_client=fake_embedding, vector_store=None)
    ctx = await svc.retrieve("RECALLDOC_gamma_3322", db, tenant_id=tid, organization_id=oid, use_cache=False)
    retrieved_ids = [str(c.chunk_id) for c in ctx.chunks]
    assert _recall_at_k(retrieved_ids, {chunk_id}, k=5) == 1.0


@pytest.mark.asyncio
async def test_citation_accuracy_grounded(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    reg = KnowledgeSourceRegistry()
    src = await reg.create_source(db, tenant_id=tid, organization_id=oid, name="s", source_type="documentation")
    await db.commit()
    await Indexer(embedding_client=fake_embedding, vector_store=None).index_source(
        db, src.id, content="GROUNDEDDOC_delta_6644 explanation text"
    )
    await db.commit()
    svc = RAGService(embedding_client=fake_embedding, vector_store=None)
    ctx = await svc.retrieve("GROUNDEDDOC_delta_6644", db, tenant_id=tid, organization_id=oid, use_cache=False)
    assert ctx.citations
    chunk_ids = {str(c.chunk_id) for c in ctx.chunks}
    assert all(c.chunk_id in chunk_ids for c in ctx.citations)
