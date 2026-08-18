"""Tests for hybrid search engine at backend/app/code_intelligence/search.py."""

import asyncio
import os
import re
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

# ── Stub `app` package before any submodule imports ───────────────────
_backend_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
if "app" not in sys.modules:
    _app = types.ModuleType("app")
    _app.__path__ = [os.path.join(_backend_dir, "app")]
    _app.__package__ = "app"
    _app.__version__ = "3.0.0-test"
    sys.modules["app"] = _app

import pytest

from app.code_intelligence.search import (
    HybridSearchEngine,
    SearchResult,
    SearchResults,
)


# ─── Helpers ─────────────────────────────────────────────────────────


def _make_engine():
    db = AsyncMock()
    return HybridSearchEngine(
        db_session=db, embedding_service=None, vector_store=None, graph_store=None
    )


def _sym_result(
    name,
    file_path="src/app.py",
    lang="python",
    score=0.5,
    sym_type="FUNCTION",
    source="lexical",
    line=10,
    content="",
    snippet="",
    rid=None,
):
    return SearchResult(
        id=rid or str(uuid.uuid4()),
        score=score,
        type="symbol",
        name=name,
        file_path=file_path,
        line=line,
        end_line=line + 20,
        content=content,
        snippet=snippet,
        language=lang,
        symbol_type=sym_type,
        retrieval_source=source,
    )


def _file_result(
    name, file_path, lang="python", score=0.5, source="metadata", rid=None
):
    return SearchResult(
        id=rid or str(uuid.uuid4()),
        score=score,
        type="file",
        name=name,
        file_path=file_path,
        language=lang,
        retrieval_source=source,
    )


# ─── TestSearchStrategies ────────────────────────────────────────────


class TestSearchStrategies:
    """Verify individual search strategies return correctly structured results."""

    @pytest.mark.asyncio
    async def test_lexical_search(self):
        engine = _make_engine()

        mock_sym = MagicMock()
        mock_sym.name = "get_user"
        mock_sym.qualified_name = "module.get_user"
        mock_sym.signature = "def get_user(user_id: int) -> dict"
        mock_sym.docstring = "Get a user by ID"
        mock_sym.symbol_type = "FUNCTION"
        mock_sym.language = "python"
        mock_sym.start_line = 10
        mock_sym.end_line = 25
        mock_sym.symbol_id = "sym-1"
        mock_sym.visibility = "public"
        mock_sym.parent_symbol_id = None

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [(mock_sym, "src/users.py")]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        engine._db.execute = AsyncMock(side_effect=side_effect)

        results = await engine.lexical_search("get_user", "repo-1", limit=10)

        assert len(results) >= 1
        first = results[0]
        assert first.type == "symbol"
        assert "get_user" in first.name
        assert first.retrieval_source == "lexical"
        assert first.file_path == "src/users.py"

    @pytest.mark.asyncio
    async def test_symbol_search(self):
        engine = _make_engine()

        mock_sym = MagicMock()
        mock_sym.name = "UserService"
        mock_sym.qualified_name = "services.UserService"
        mock_sym.symbol_type = "CLASS"
        mock_sym.language = "python"
        mock_sym.start_line = 5
        mock_sym.end_line = 100
        mock_sym.symbol_id = "sym-2"
        mock_sym.signature = "class UserService"
        mock_sym.docstring = "User management service"
        mock_sym.visibility = "public"
        mock_sym.parent_symbol_id = None

        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_sym, "src/services/user_service.py")]

        engine._db.execute = AsyncMock(return_value=mock_result)

        results = await engine.symbol_search("UserService", "repo-1", limit=10)

        assert len(results) >= 1
        assert results[0].type == "symbol"
        assert results[0].name == "UserService"
        assert results[0].retrieval_source == "symbol"

    @pytest.mark.asyncio
    async def test_file_search(self):
        engine = _make_engine()

        mock_file = MagicMock()
        mock_file.id = uuid.uuid4()
        mock_file.file_path = "src/services/user_service.py"
        mock_file.file_name = "user_service.py"
        mock_file.language = "python"
        mock_file.line_count = 100
        mock_file.symbol_count = 5
        mock_file.is_test_file = False
        mock_file.is_config_file = False
        mock_file.is_documentation = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_file]

        engine._db.execute = AsyncMock(return_value=mock_result)

        results = await engine.file_search("user_service", "repo-1", limit=10)

        assert len(results) >= 1
        assert results[0].type == "file"
        assert "user_service.py" in results[0].file_path
        assert results[0].score > 0

    @pytest.mark.asyncio
    async def test_regex_search(self):
        engine = _make_engine()

        mock_sym = MagicMock()
        mock_sym.name = "async_handler"
        mock_sym.qualified_name = "handlers.async_handler"
        mock_sym.signature = "async def async_handler(request)"
        mock_sym.docstring = "An async request handler"
        mock_sym.symbol_type = "FUNCTION"
        mock_sym.language = "python"
        mock_sym.start_line = 20
        mock_sym.end_line = 50
        mock_sym.symbol_id = "sym-3"

        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_sym, "src/handlers.py")]

        engine._db.execute = AsyncMock(return_value=mock_result)

        results = await engine.regex_search(r"async.*handler", "repo-1", limit=10)

        assert len(results) >= 1
        assert results[0].type == "symbol"
        assert results[0].score > 0


# ─── TestResultCombination ───────────────────────────────────────────


class TestResultCombination:
    """Verify result combination, deduplication, and filtering."""

    def test_rrf_combination(self):
        engine = _make_engine()
        shared_id = "shared-id"

        r1 = _sym_result("func_a", score=0.9, source="lexical", rid=shared_id)
        r2 = _sym_result("func_b", score=0.7, source="semantic", rid="other-id")
        r3 = _sym_result("func_a", score=0.8, source="symbol", rid=shared_id)

        combined = engine._reciprocal_rank_fusion([[r1, r2], [r3]])

        assert len(combined) == 2

        func_a = next(r for r in combined if r.id == shared_id)
        func_b = next(r for r in combined if r.id == "other-id")
        assert func_a.score > func_b.score

    def test_deduplication(self):
        engine = _make_engine()
        id_val = "dedup-id"

        r1 = _sym_result("func", score=0.9, source="lexical", rid=id_val)
        r2 = _sym_result("func", score=0.8, source="symbol", rid=id_val)

        combined = engine._reciprocal_rank_fusion([[r1], [r2]])

        ids = [r.id for r in combined]
        assert ids.count(id_val) == 1

        merged = next(r for r in combined if r.id == id_val)
        assert merged.retrieval_source == "hybrid"

    def test_apply_filters(self):
        engine = _make_engine()
        r1 = _sym_result("func_a", lang="python", sym_type="FUNCTION")
        r2 = _sym_result("func_b", lang="typescript", sym_type="CLASS")
        r3 = _file_result("app.py", "src/app.py", lang="python")

        results = [r1, r2, r3]

        filtered = engine._apply_filters(results, {"language": "python"})
        assert len(filtered) == 2
        assert all(r.language == "python" for r in filtered)

        filtered_type = engine._apply_filters(results, {"type": "function"})
        assert len(filtered_type) == 1
        assert filtered_type[0].symbol_type == "FUNCTION"

        filtered_path = engine._apply_filters(results, {"path_pattern": "src/*"})
        assert len(filtered_path) == 3


# ─── TestRanking ─────────────────────────────────────────────────────


class TestRanking:
    """Verify multi-factor ranking logic."""

    def test_lexical_relevance(self):
        engine = _make_engine()
        tokens = {"get", "user"}

        high_match = _sym_result(
            "get_user",
            content="get the user by id",
            snippet="def get_user(user_id)",
        )
        low_match = _sym_result(
            "delete_item",
            content="item removal",
            snippet="def delete_item(item_id)",
        )

        high_score = engine._lexical_relevance(high_match, tokens)
        low_score = engine._lexical_relevance(low_match, tokens)

        assert high_score > low_score
        assert high_score > 0.0

    def test_symbol_relevance(self):
        engine = _make_engine()
        tokens = {"get", "user"}

        exact_name = _sym_result("get_user")
        partial_name = _sym_result("get_order")
        unrelated_name = _sym_result("delete_item")

        exact_score = engine._symbol_relevance(exact_name, tokens)
        partial_score = engine._symbol_relevance(partial_name, tokens)
        unrelated_score = engine._symbol_relevance(unrelated_name, tokens)

        assert exact_score >= partial_score
        assert exact_score > unrelated_score

    def test_recency_ranking(self):
        engine = _make_engine()
        now = datetime.now(timezone.utc)

        recent = _sym_result("recent_func")
        recent.metadata = {"commit_date": (now - timedelta(days=3)).isoformat()}

        old = _sym_result("old_func")
        old.metadata = {"commit_date": (now - timedelta(days=120)).isoformat()}

        no_date = _sym_result("no_date_func")

        recent_score = engine._recency_score(recent)
        old_score = engine._recency_score(old)
        no_date_score = engine._recency_score(no_date)

        assert recent_score == 1.0
        assert recent_score > old_score
        assert old_score <= 0.5
        assert no_date_score == 0.2


# ─── TestSearchResult ────────────────────────────────────────────────


class TestSearchResult:
    """Verify SearchResult dataclass fields and citations."""

    def test_result_fields(self):
        result = SearchResult(
            id="sym-123",
            score=0.85,
            type="symbol",
            name="my_function",
            file_path="src/app.py",
            line=42,
            end_line=60,
            content="A helper function",
            snippet="def my_function()",
            language="python",
            symbol_type="FUNCTION",
            repository="repo-abc",
            commit="def456",
            metadata={"key": "value"},
            highlights=["highlight 1"],
            citations=[{"source": "docs.md", "line": 10}],
            retrieval_source="hybrid",
        )

        assert result.id == "sym-123"
        assert result.score == 0.85
        assert result.type == "symbol"
        assert result.name == "my_function"
        assert result.file_path == "src/app.py"
        assert result.line == 42
        assert result.end_line == 60
        assert result.content == "A helper function"
        assert result.snippet == "def my_function()"
        assert result.language == "python"
        assert result.symbol_type == "FUNCTION"
        assert result.repository == "repo-abc"
        assert result.commit == "def456"
        assert result.metadata == {"key": "value"}
        assert result.highlights == ["highlight 1"]
        assert result.retrieval_source == "hybrid"

    def test_citations_preserved(self):
        citations = [
            {"source": "docs/api.md", "line": 15, "text": "API reference"},
            {"source": "README.md", "line": 30, "text": "Usage example"},
        ]
        result = SearchResult(
            id="sym-456",
            name="api_handler",
            citations=citations,
        )

        assert len(result.citations) == 2
        assert result.citations[0]["source"] == "docs/api.md"
        assert result.citations[1]["text"] == "Usage example"

        result.score = 0.95
        result.retrieval_source = "hybrid"
        assert len(result.citations) == 2
        assert result.citations[0]["line"] == 15
