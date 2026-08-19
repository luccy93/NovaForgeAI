"""Volume 43 — RAG retrieval tests (DB + fake embedding)."""

import uuid

import pytest
from sqlalchemy import select

from app.rag.exceptions import InsufficientEvidenceError
from app.rag.ingestion import Indexer, KnowledgeSourceRegistry
from app.rag.models import RagRetrievalLog
from app.rag.retrieval.service import RAGService


async def _seed(db, tenant_id, org_id, phrase, fake_embedding, source_type="documentation"):
    reg = KnowledgeSourceRegistry()
    src = await reg.create_source(
        db, tenant_id=tenant_id, organization_id=org_id, name="doc-" + str(uuid.uuid4()),
        source_type=source_type,
    )
    await db.commit()
    await Indexer(embedding_client=fake_embedding, vector_store=None).index_source(db, src.id, content=phrase)
    await db.commit()
    return src


@pytest.mark.asyncio
async def test_retrieve_finds_indexed_doc(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    phrase = "UNIQUEPHRASE_retrieval_alpha_9981 the quick brown fox"
    await _seed(db, tid, oid, phrase, fake_embedding)
    svc = RAGService(embedding_client=fake_embedding, vector_store=None)
    ctx = await svc.retrieve("UNIQUEPHRASE_retrieval_alpha_9981", db, tenant_id=tid, organization_id=oid, use_cache=False)
    assert ctx.answerability != "INSUFFICIENT"
    assert any("UNIQUEPHRASE_retrieval_alpha_9981" in (c.content or "") for c in ctx.chunks)
    logs = (await db.execute(select(RagRetrievalLog).where(RagRetrievalLog.tenant_id == tid))).scalars().all()
    assert logs and logs[-1].lexical_count >= 1


@pytest.mark.asyncio
async def test_retrieve_empty_raises_insufficient(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    await _seed(db, tid, oid, "real content present here zzz", fake_embedding)
    svc = RAGService(embedding_client=fake_embedding, vector_store=None)
    with pytest.raises(InsufficientEvidenceError):
        await svc.retrieve("zzz_nomatch_phrase_qqq_12345_never_indexed", db, tenant_id=tid, organization_id=oid, use_cache=False)


@pytest.mark.asyncio
async def test_retrieve_records_grounded_citations(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    phrase = "CITEDOC_beta_7741 function returns a value"
    await _seed(db, tid, oid, phrase, fake_embedding)
    svc = RAGService(embedding_client=fake_embedding, vector_store=None)
    ctx = await svc.retrieve("CITEDOC_beta_7741", db, tenant_id=tid, organization_id=oid, use_cache=False)
    assert len(ctx.citations) >= 1
    for cit in ctx.citations:
        chunk = next(c for c in ctx.chunks if str(c.chunk_id) == cit.chunk_id)
        assert cit.snippet in (chunk.content or "")
