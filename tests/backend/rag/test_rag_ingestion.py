"""Volume 43 — RAG ingestion tests (DB + fake embedding)."""

import uuid

import pytest
from sqlalchemy import select

from app.rag.ingestion import Indexer, KnowledgeSourceRegistry
from app.rag.models import KnowledgeSource, KnowledgeSourceVersion, RagChunk


async def _index_doc(db, tenant_id, org_id, content, fake_embedding, source_type="documentation"):
    reg = KnowledgeSourceRegistry()
    src = await reg.create_source(
        db, tenant_id=tenant_id, organization_id=org_id, name="doc-" + str(uuid.uuid4()),
        source_type=source_type,
    )
    await db.commit()
    version_id = await Indexer(embedding_client=fake_embedding, vector_store=None).index_source(
        db, src.id, content=content
    )
    await db.commit()
    return src, version_id


@pytest.mark.asyncio
async def test_create_source_persists(db):
    reg = KnowledgeSourceRegistry()
    tid = uuid.uuid4()
    src = await reg.create_source(db, tenant_id=tid, organization_id=uuid.uuid4(), name="s", source_type="documentation")
    await db.commit()
    assert src.id is not None
    got = await reg.get_source(db, src.id)
    assert got is not None and got.tenant_id == tid


@pytest.mark.asyncio
async def test_index_source_creates_chunks_and_version(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    src, version_id = await _index_doc(db, tid, oid, "# Heading\nBody one.\n\n## Sub\nBody two.", fake_embedding, source_type="markdown")
    chunks = (await db.execute(select(RagChunk).where(RagChunk.source_id == src.id))).scalars().all()
    assert len(chunks) >= 1
    assert all(c.tenant_id == tid for c in chunks)
    assert chunks[0].embedding_model == "fake"
    ver = (await db.execute(select(KnowledgeSourceVersion).where(KnowledgeSourceVersion.id == version_id))).scalar_one()
    assert ver.is_active is True and ver.validated is True
    refreshed = (await db.execute(select(KnowledgeSource).where(KnowledgeSource.id == src.id))).scalar_one()
    assert refreshed.status == "validated"
    assert refreshed.active_version_id == version_id


@pytest.mark.asyncio
async def test_delete_propagation_soft_deletes(db, fake_embedding):
    tid, oid = uuid.uuid4(), uuid.uuid4()
    src, _ = await _index_doc(db, tid, oid, "unique content alpha beta gamma delta epsilon", fake_embedding, source_type="documentation")
    await Indexer(embedding_client=fake_embedding, vector_store=None).delete_propagation(db, src.id)
    await db.commit()
    chunks = (await db.execute(select(RagChunk).where(RagChunk.source_id == src.id))).scalars().all()
    assert all(c.is_deleted for c in chunks)
    refreshed = (await db.execute(select(KnowledgeSource).where(KnowledgeSource.id == src.id))).scalar_one()
    assert refreshed.status == "deleted"


@pytest.mark.asyncio
async def test_markdown_index_produces_multiple_chunks(db, fake_embedding):
    content = "# A\nPara A.\n\n# B\nPara B.\n\n# C\nPara C."
    src, _ = await _index_doc(db, uuid.uuid4(), uuid.uuid4(), content, fake_embedding, source_type="markdown")
    chunks = (await db.execute(select(RagChunk).where(RagChunk.source_id == src.id))).scalars().all()
    assert len(chunks) >= 3
