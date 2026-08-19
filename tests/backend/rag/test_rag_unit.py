"""Volume 43 — RAG unit tests (no external services)."""

import uuid

import pytest

from app.rag.config import ContextBudget, RagConfig
from app.rag.ingestion import Chunker, DocumentParser
from app.rag.retrieval.assembly import ContextAssembler
from app.rag.retrieval.fusion import Reranker, reciprocal_rank_fusion
from app.rag.retrieval.query import classify_query, expand_query, route_query
from app.rag.schemas import Answerability, RetrievedChunk


def _chunk(chunk_id, content="x", **kw):
    base = dict(chunk_id=str(chunk_id), content=content, retrieval_method="hybrid", scores={})
    base.update(kw)
    return RetrievedChunk(**base)


def test_markdown_split_on_headings():
    md = "# Title\nIntro text.\n\n## Section A\nBody A.\n\n## Section B\nBody B."
    parsed = DocumentParser().parse(md, "markdown")
    headings = [s.heading for s in parsed.sections]
    assert "Title" in headings
    assert "Section A" in headings and "Section B" in headings
    assert any("Body A" in s.text for s in parsed.sections)
    assert parsed.code_blocks == 0


def test_markdown_extracts_code_blocks_and_links():
    md = "Text\n\n```python\nx = 1\n```\n\nSee [docs](https://example.com)."
    parsed = DocumentParser().parse(md, "markdown")
    assert parsed.code_blocks == 1
    assert "https://example.com" in parsed.links


def test_plain_text_paragraph_chunking():
    text = "Para one.\n\nPara two.\n\nPara three."
    parsed = DocumentParser().parse(text, "plain")
    assert len(parsed.sections) == 3


def test_oversized_section_is_split():
    big = "word " * 2000
    parsed = DocumentParser().parse(big, "plain")
    chunked = Chunker().chunk(parsed)
    assert len(chunked) >= 2
    assert all(len(c.text) <= 1500 for c in chunked)


def test_classify_where_is_symbol_lookup():
    assert classify_query("Where is auth implemented?").intent == "symbol_lookup"


def test_classify_find_function_symbol_lookup():
    assert classify_query("Find exact function process_data").intent == "symbol_lookup"


def test_route_query_returns_plan():
    plan = route_query("How does the auth flow work?")
    assert plan.intent == "architecture"
    assert "lexical" in plan.weights and "semantic" in plan.weights


def test_expand_query_adds_terms():
    terms = expand_query("Find function validate_input in utils")
    assert "validate_input" in terms and "utils" in terms


def test_reciprocal_rank_fusion_merges_and_ranks():
    a = _chunk(uuid.uuid4(), scores={"lexical": 0.9})
    b = _chunk(uuid.uuid4(), scores={"vector": 0.8})
    c = _chunk(a.chunk_id, scores={"vector": 0.7})
    fused = reciprocal_rank_fusion(
        {"lexical": [a], "vector": [b, c]}, weights={"lexical": 1.0, "vector": 1.0}, k=60
    )
    ids = [f.chunk_id for f in fused]
    assert ids.count(str(a.chunk_id)) == 1
    assert str(a.chunk_id) in ids and str(b.chunk_id) in ids
    assert fused[0].chunk_id == str(a.chunk_id)
    assert fused[0].scores["rrf"] > fused[1].scores["rrf"]


def test_reranker_rrf_strategy_sorts_by_rrf():
    chunks = [_chunk(uuid.uuid4(), scores={"rrf": 0.1}), _chunk(uuid.uuid4(), scores={"rrf": 0.5})]
    out = Reranker().rerank(chunks, "q", strategy="rrf")
    assert out[0].scores["rrf"] == 0.5


def test_reranker_weighted_sort_by_semantic():
    chunks = [
        _chunk(uuid.uuid4(), scores={"rrf": 0.0, "semantic": 0.1, "graph": 0.0, "symbol": 0.0}),
        _chunk(uuid.uuid4(), scores={"rrf": 0.0, "semantic": 0.9, "graph": 0.0, "symbol": 0.0}),
    ]
    out = Reranker().rerank(chunks, "q", strategy="weighted")
    assert out[0].scores["semantic"] == 0.9
    assert "rerank" in out[0].scores


def test_assembler_empty_is_insufficient():
    ctx = ContextAssembler().assemble([])
    assert ctx.answerability == Answerability.INSUFFICIENT.value
    assert ctx.chunks == []


def test_assembler_two_chunks_partial():
    chunks = [
        _chunk(uuid.uuid4(), content="alpha content here", scores={"rerank": 0.6}),
        _chunk(uuid.uuid4(), content="beta content here", scores={"rerank": 0.4}),
    ]
    ctx = ContextAssembler().assemble(chunks)
    assert ctx.answerability == Answerability.PARTIAL.value
    assert len(ctx.chunks) == 2 and len(ctx.citations) == 2


def test_assembler_high_confidence_when_strong():
    chunks = [
        _chunk(uuid.uuid4(), content="alpha content here", scores={"rerank": 0.9}),
        _chunk(uuid.uuid4(), content="beta content here", scores={"rerank": 0.8}),
        _chunk(uuid.uuid4(), content="gamma content here", scores={"rerank": 0.7}),
        _chunk(uuid.uuid4(), content="delta content here", scores={"rerank": 0.6}),
    ]
    ctx = ContextAssembler().assemble(chunks)
    assert ctx.answerability == Answerability.HIGH_CONFIDENCE.value
    assert "Question" not in ctx.context_text


def test_assembler_respects_token_budget():
    cfg = RagConfig(
        budget=ContextBudget(total=200, retrieval=80, system=20, conversation=20, code=20, tools=20, output=20)
    )
    small = "word " * 10
    chunks = [_chunk(uuid.uuid4(), content=f"{small}{i}", scores={"rerank": 0.9 - i * 0.1}) for i in range(5)]
    ctx = ContextAssembler(cfg).assemble(chunks)
    assert ctx.token_count <= 81  # 5 * ~12 tokens well within the 80 retrieval budget
    assert len(ctx.chunks) == 5


def test_assembler_dedup_near_identical():
    chunks = [
        _chunk(uuid.uuid4(), content="same text here", scores={"rerank": 0.9}),
        _chunk(uuid.uuid4(), content="same text here", scores={"rerank": 0.8}),
    ]
    ctx = ContextAssembler().assemble(chunks)
    assert len(ctx.chunks) == 1


def test_context_budget_requires_positive_total():
    with pytest.raises(ValueError):
        ContextBudget(total=0)
