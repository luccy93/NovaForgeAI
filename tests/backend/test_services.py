"""Unit tests for core services — embeddings, vector store, graph store, RAG, citation, code analysis, repo importer."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.code_analysis import CodeAnalysisService
from app.services.citation import CitationEngine
from app.services.repo_importer import RepoImporter, GitImportError


# ─── Code Analysis ─────────────────────────────────────────────────

class TestCodeAnalysisService:
    def test_analyze_python_functions(self, sample_python_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_python_code, "python")
        assert result["language"] == "python"
        names = [f["name"] for f in result["functions"]]
        assert "__init__" in names
        assert "get_user" in names
        assert "create_user" in names

    def test_analyze_python_classes(self, sample_python_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_python_code, "python")
        names = [c["name"] for c in result["classes"]]
        assert "UserService" in names

    def test_analyze_python_dependencies(self, sample_python_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_python_code, "python")
        assert "os" in result["dependencies"]
        assert "typing" in result["dependencies"]

    def test_analyze_typescript(self, sample_typescript_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_typescript_code, "typescript")
        assert result["language"] == "typescript"
        names = [f["name"] for f in result["functions"]]
        assert "ngOnInit" in names
        assert "loadData" in names

    def test_analyze_typescript_classes(self, sample_typescript_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_typescript_code, "typescript")
        names = [c["name"] for c in result["classes"]]
        assert "AppComponent" in names

    def test_analyze_go(self, sample_go_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_go_code, "go")
        assert result["language"] == "go"
        names = [f["name"] for f in result["functions"]]
        assert "main" in names
        assert "handler" in names

    def test_analyze_rust(self, sample_rust_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_rust_code, "rust")
        assert result["language"] == "rust"
        names = [f["name"] for f in result["functions"]]
        assert "main" in names
        assert "calculate" in names

    def test_analyze_java(self, sample_java_code):
        svc = CodeAnalysisService()
        result = svc.analyze_file(sample_java_code, "java")
        assert result["language"] == "java"
        names = [c["name"] for c in result["classes"]]
        assert "NovaForgeApplication" in names

    def test_complexity_simple(self):
        svc = CodeAnalysisService()
        content = "def foo():\n    pass"
        result = svc.analyze_file(content, "python")
        assert result["complexity"] >= 1

    def test_complexity_with_branches(self):
        svc = CodeAnalysisService()
        content = """def check(x):
    if x > 0:
        if x > 10:
            return True
    return False"""
        result = svc.analyze_file(content, "python")
        assert result["complexity"] >= 3

    def test_unsupported_language(self):
        svc = CodeAnalysisService()
        with pytest.raises(ValueError, match="Unsupported language"):
            svc.analyze_file("content", "ruby")

    def test_empty_content(self):
        svc = CodeAnalysisService()
        result = svc.analyze_file("", "python")
        assert result["size_bytes"] == 0
        assert result["functions"] == []
        assert result["classes"] == []

    def test_line_count(self):
        svc = CodeAnalysisService()
        content = "line1\nline2\nline3"
        result = svc.analyze_file(content, "python")
        assert result["line_count"] == 3

    def test_multiple_files_same_parser(self):
        svc = CodeAnalysisService()
        r1 = svc.analyze_file("def a(): pass", "python")
        r2 = svc.analyze_file("def b(): pass", "python")
        assert len(r1["functions"]) == 1
        assert len(r2["functions"]) == 1

    def test_extract_functions_with_decorators(self):
        svc = CodeAnalysisService()
        content = """
@decorator
@another_decorator
def decorated_func():
    pass
"""
        result = svc.analyze_file(content, "python")
        names = [f["name"] for f in result["functions"]]
        assert "decorated_func" in names

    def test_extract_nested_functions(self):
        svc = CodeAnalysisService()
        content = """
def outer():
    def inner():
        pass
    return inner
"""
        result = svc.analyze_file(content, "python")
        names = [f["name"] for f in result["functions"]]
        assert "outer" in names

    def test_dependencies_no_duplicates(self):
        svc = CodeAnalysisService()
        content = "import os\nimport os\nfrom os import path"
        result = svc.analyze_file(content, "python")
        assert result["dependencies"].count("os") == 1


# ─── Citation Engine ───────────────────────────────────────────────

class TestCitationEngine:
    def test_format_response_single_source(self):
        engine = CitationEngine()
        result = engine.format_response(
            answer="Python is great.",
            sources=[{"text": "Python docs", "source": "docs.python.org", "type": "web", "score": 0.95}],
            confidence=0.95,
            model_used="gpt-4o-mini",
        )
        assert len(result.citations) == 1
        assert result.citations[0].id == 1
        assert result.citations[0].source == "docs.python.org"
        assert result.citations[0].source_type == "web"
        assert result.citations[0].relevance_score == 0.95
        assert result.confidence == 0.95
        assert result.model_used == "gpt-4o-mini"

    def test_format_response_multiple_sources(self):
        engine = CitationEngine()
        sources = [
            {"text": "Source A", "source": "A", "type": "vector", "score": 0.9},
            {"text": "Source B", "source": "B", "type": "graph", "score": 0.8},
            {"text": "Source C", "source": "C", "type": "web", "score": 0.7},
        ]
        result = engine.format_response("Answer.", sources, confidence=0.8, model_used="test")
        assert len(result.citations) == 3
        assert result.citations[0].id == 1
        assert result.citations[2].id == 3

    def test_format_response_annotated_answer(self):
        engine = CitationEngine()
        result = engine.format_response(
            answer="Python is a programming language.",
            sources=[{"text": "Python wiki", "source": "wiki", "type": "web", "score": 0.9}],
            confidence=0.9,
            model_used="test",
        )
        assert result.answer.startswith("Python is a programming language.")
        assert "Sources:" in result.answer

    def test_empty_response(self):
        engine = CitationEngine()
        result = engine.empty_response("No context found.")
        assert result.answer == "No context found."
        assert result.citations == []
        assert result.confidence == 0.0
        assert result.model_used == ""

    def test_empty_response_default_message(self):
        engine = CitationEngine()
        result = engine.empty_response()
        assert result.answer == "No relevant context found."

    def test_format_response_no_sources(self):
        engine = CitationEngine()
        result = engine.format_response("Answer.", [], confidence=0.0, model_used="test")
        assert result.answer == "Answer."

    def test_source_with_content_fallback(self):
        engine = CitationEngine()
        result = engine.format_response(
            "Answer.",
            [{"content": "Fallback content", "source": "test", "type": "vector", "score": 0.5}],
            confidence=0.5,
            model_used="test",
        )
        assert result.citations[0].text == "Fallback content"


# ─── Repo Importer ─────────────────────────────────────────────────

class TestRepoImporter:
    @pytest.mark.asyncio
    async def test_import_invalid_path(self):
        importer = RepoImporter(db=MagicMock())
        with pytest.raises(GitImportError, match="Not a directory"):
            await importer.import_from_path(
                "00000000-0000-0000-0000-000000000000",
                "/nonexistent/path",
            )

    @pytest.mark.asyncio
    async def test_import_from_path_empty_dir(self, tmp_path):
        importer = RepoImporter(db=MagicMock())
        result = await importer.import_from_path(
            "00000000-0000-0000-0000-000000000000",
            str(tmp_path),
        )
        assert result["files_indexed"] == 0
        assert result["functions_found"] == 0

    @pytest.mark.asyncio
    async def test_import_from_path_with_python_files(self, tmp_path):
        py_file = tmp_path / "main.py"
        py_file.write_text("def hello():\n    print('hello')\n")
        importer = RepoImporter(db=MagicMock())
        result = await importer.import_from_path(
            "00000000-0000-0000-0000-000000000000",
            str(tmp_path),
        )
        assert result["files_indexed"] >= 1

    @pytest.mark.asyncio
    async def test_import_skips_node_modules(self, tmp_path):
        node_modules = tmp_path / "node_modules" / "lib.js"
        node_modules.parent.mkdir(parents=True)
        node_modules.write_text("var x = 1;")
        importer = RepoImporter(db=MagicMock())
        result = await importer.import_from_path(
            "00000000-0000-0000-0000-000000000000",
            str(tmp_path),
        )
        assert result["files_indexed"] == 0

    @pytest.mark.asyncio
    async def test_import_skips_pycache(self, tmp_path):
        pycache = tmp_path / "__pycache__" / "module.py"
        pycache.parent.mkdir(parents=True)
        pycache.write_text("x = 1")
        importer = RepoImporter(db=MagicMock())
        result = await importer.import_from_path(
            "00000000-0000-0000-0000-000000000000",
            str(tmp_path),
        )
        assert result["files_indexed"] == 0

    def test_git_import_error_message(self):
        exc = GitImportError("git clone failed")
        assert "git clone failed" in str(exc)

    @pytest.mark.asyncio
    async def test_import_handles_binary_files(self, tmp_path):
        bin_file = tmp_path / "data.bin"
        bin_file.write_bytes(b"\x00\x01\x02\xff")
        importer = RepoImporter(db=MagicMock())
        result = await importer.import_from_path(
            "00000000-0000-0000-0000-000000000000",
            str(tmp_path),
        )
        assert result["files_indexed"] == 0
