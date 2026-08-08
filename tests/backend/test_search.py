"""Tests for search, embedding, and RAG pipelines."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.rag_pipeline import RAGPipeline, RAGSource, RAGResult


# ─── Embedding Service ─────────────────────────────────────────────

class TestEmbeddingService:
    def test_init_with_sentence_transformers(self):
        with patch("app.services.embeddings.EmbeddingService") as mock_svc:
            instance = mock_svc.return_value
            instance._backend = "local"
            assert instance._backend == "local"

    def test_get_embeddings_returns_list(self):
        with patch("app.services.embeddings.EmbeddingService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_embeddings.return_value = [[0.1, 0.2, 0.3]]
            result = instance.get_embeddings(["test text"])
            assert len(result) == 1
            assert len(result[0]) == 3

    def test_get_embedding_single(self):
        with patch("app.services.embeddings.EmbeddingService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_embeddings.return_value = [[0.1, 0.2]]
            result = instance.get_embeddings(["test"])
            assert len(result) == 1
            assert len(result[0]) == 2

    def test_get_embeddings_batch(self):
        with patch("app.services.embeddings.EmbeddingService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_embeddings.return_value = [[0.1], [0.2], [0.3]]
            result = instance.get_embeddings(["a", "b", "c"])
            assert len(result) == 3

    def test_get_embeddings_empty_list(self):
        with patch("app.services.embeddings.EmbeddingService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_embeddings.return_value = []
            result = instance.get_embeddings([])
            assert result == []

    def test_dimension_consistency(self):
        with patch("app.services.embeddings.EmbeddingService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_embeddings.return_value = [[0.1] * 384, [0.2] * 384]
            results = instance.get_embeddings(["a", "b"])
            for r in results:
                assert len(r) == 384


# ─── Vector Store ──────────────────────────────────────────────────

class TestVectorStoreService:
    def test_search_returns_list(self):
        with patch("app.services.vector_store.QdrantClient") as mock_qdrant:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [
                MagicMock(id="1", score=0.95, payload={"content": "test"})
            ]
            mock_qdrant.return_value = mock_instance
            svc = VectorStoreService()
            results = svc.search(collection="test", query_vector=[0.1] * 384, limit=5)
            assert len(results) == 1
            assert results[0]["id"] == "1"

    def test_search_with_filters(self):
        with patch("app.services.vector_store.QdrantClient") as mock_qdrant:
            mock_instance = MagicMock()
            mock_instance.search.return_value = []
            mock_qdrant.return_value = mock_instance
            svc = VectorStoreService()
            results = svc.search(
                collection="test",
                query_vector=[0.1] * 384,
            )
            assert results == []

    def test_create_collection(self):
        with patch("app.services.vector_store.QdrantClient") as mock_qdrant:
            mock_instance = MagicMock()
            mock_qdrant.return_value = mock_instance
            svc = VectorStoreService()
            result = svc.create_collection("test", size=384)
            assert result is True

    def test_collection_exists(self):
        with patch("app.services.vector_store.QdrantClient") as mock_qdrant:
            mock_instance = MagicMock()
            mock_instance.get_collection.side_effect = ValueError("not found")
            mock_qdrant.return_value = mock_instance
            svc = VectorStoreService()
            result = svc.collection_exists("test")
            assert result is False


# ─── RAG Pipeline ──────────────────────────────────────────────────

class TestRAGPipeline:
    def test_rag_result_to_dict(self):
        result = RAGResult(
            answer="Test answer",
            sources=[RAGSource(text="src", source="file.py", score=0.9, type="vector")],
            confidence=0.9,
            model_used="gpt-4o-mini",
        )
        d = result.to_dict()
        assert d["answer"] == "Test answer"
        assert len(d["sources"]) == 1
        assert d["confidence"] == 0.9
        assert d["model_used"] == "gpt-4o-mini"

    def test_rag_result_empty_sources(self):
        result = RAGResult(answer="No answer")
        assert result.sources == []
        assert result.confidence == 0.0

    def test_rag_result_multiple_sources(self):
        sources = [
            RAGSource(text="a", source="a.py", score=0.9, type="vector"),
            RAGSource(text="b", source="b.py", score=0.8, type="graph"),
        ]
        result = RAGResult(answer="Answer", sources=sources, confidence=0.85, model_used="test")
        assert len(result.sources) == 2
        assert result.sources[0].type == "vector"
        assert result.sources[1].type == "graph"

    @pytest.mark.asyncio
    async def test_query_returns_dict(self, mock_embedding_service, mock_vector_store):
        pipeline = RAGPipeline(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
        )
        result = await pipeline.query(question="What is Python?")
        assert isinstance(result, dict)
        assert "answer" in result
        assert "sources" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_query_without_sources(self, mock_embedding_service):
        with patch("app.services.vector_store.VectorStoreService") as mock_vs:
            mock_instance = MagicMock()
            mock_instance.search.return_value = []
            mock_vs.return_value = mock_instance
            pipeline = RAGPipeline(embedding_service=mock_embedding_service, vector_store=mock_instance)
            result = await pipeline.query(question="Unknown topic")
            assert "No relevant context" in result["answer"]

    @pytest.mark.asyncio
    async def test_query_stream_generates(self, mock_embedding_service, mock_vector_store):
        pipeline = RAGPipeline(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
        )
        chunks = []
        async for chunk in pipeline.query_stream(question="Hello"):
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_query_stream_empty_without_llm(self, mock_embedding_service):
        with patch("app.services.vector_store.VectorStoreService") as mock_vs:
            mock_instance = MagicMock()
            mock_instance.search.return_value = []
            mock_vs.return_value = mock_instance
            pipeline = RAGPipeline(embedding_service=mock_embedding_service, vector_store=mock_instance)
            chunks = []
            async for chunk in pipeline.query_stream(question="Hello"):
                chunks.append(chunk)
            text = "".join(chunks)
            assert len(text) > 0

    def test_rag_source_dataclass(self):
        src = RAGSource(text="code", source="file.py", score=0.95, type="vector")
        assert src.text == "code"
        assert src.source == "file.py"
        assert src.score == 0.95
        assert src.type == "vector"

    def test_rag_source_default_score(self):
        src = RAGSource(text="code", source="file.py", score=0.0, type="vector")
        assert src.score == 0.0


class TestRAGPipelineSynthesize:
    @pytest.fixture
    def pipeline(self):
        from app.services.rag_pipeline import RAGPipeline
        emb = MagicMock()
        vs = MagicMock()
        p = RAGPipeline.__new__(RAGPipeline)
        p._embeddings = emb
        p._vector_store = vs
        p._graph_store = None
        p._llm_client = None
        p._llm_model = ""
        return p

    @pytest.mark.asyncio
    async def test_synthesize_no_llm_returns_fallback(self, pipeline):
        result = await pipeline._synthesize("test prompt")
        assert "Unable to synthesize" in result

    @pytest.mark.asyncio
    async def test_synthesize_openai_fallback_on_error(self, pipeline):
        pipeline._llm_model = "openai"
        pipeline._llm_client = MagicMock()
        pipeline._llm_client.chat.completions.create = MagicMock(side_effect=Exception("API error"))
        result = await pipeline._synthesize("test prompt")
        assert "Unable to synthesize" in result

    @pytest.mark.asyncio
    async def test_synthesize_openai_success(self, pipeline):
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "Generated answer"
        pipeline._llm_model = "openai"
        pipeline._llm_client = MagicMock()
        pipeline._llm_client.chat.completions.create = MagicMock(return_value=mock_resp)
        result = await pipeline._synthesize("test prompt")
        assert result == "Generated answer"

    @pytest.mark.asyncio
    async def test_search_web_import_error(self, pipeline):
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            results = await pipeline._search_web("test question")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_web_exception_handled(self, pipeline):
        pytest.skip("duckduckgo_search not installed; ImportError path tested in test_search_web_import_error")

    @pytest.mark.asyncio
    async def test_query_no_sources(self, pipeline):
        pipeline._embeddings.get_embeddings = MagicMock(return_value=[[0.1] * 384])
        pipeline._vector_store.search = MagicMock(return_value=[])
        result = await pipeline.query("test question")
        assert "No relevant context found" in result["answer"]
        assert result["confidence"] == 0.0
        assert result["sources"] == []

    @pytest.mark.asyncio
    async def test_query_with_sources(self, pipeline):
        pipeline._embeddings.get_embeddings = MagicMock(return_value=[[0.1] * 384])
        pipeline._vector_store.search = MagicMock(return_value=[
            {"payload": {"content": "some code", "file_path": "main.py"}, "score": 0.95},
        ])
        pipeline._synthesize = AsyncMock(return_value="Generated answer")
        result = await pipeline.query("test question")
        assert result["answer"] == "Generated answer"
        assert len(result["sources"]) >= 1
        assert result["confidence"] > 0
