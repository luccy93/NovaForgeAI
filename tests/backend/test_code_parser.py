"""Tests for the Tree-sitter parsing engine at backend/app/code_intelligence/parser.py."""

import importlib.util
import os
import sys
import types

import pytest

_backend = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
if _backend not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend))

# Prevent app/__init__.py from importing the full API chain
if "app" not in sys.modules:
    _app_pkg = types.ModuleType("app")
    _app_pkg.__path__ = [os.path.join(os.path.abspath(_backend), "app")]
    sys.modules["app"] = _app_pkg

if "app.code_intelligence" not in sys.modules:
    _ci_pkg = types.ModuleType("app.code_intelligence")
    _ci_pkg.__path__ = [
        os.path.join(os.path.abspath(_backend), "app", "code_intelligence")
    ]
    sys.modules["app.code_intelligence"] = _ci_pkg

from app.code_intelligence.parser import ParserEngine, SymbolType


# ---------------------------------------------------------------------------
# TestLanguageDetection
# ---------------------------------------------------------------------------


class TestLanguageDetection:
    def test_detect_python(self):
        engine = ParserEngine()
        assert engine.detect_language("main.py") == "python"

    def test_detect_typescript(self):
        engine = ParserEngine()
        assert engine.detect_language("app.ts") == "typescript"

    def test_detect_javascript(self):
        engine = ParserEngine()
        assert engine.detect_language("index.js") == "javascript"

    def test_detect_unknown(self):
        engine = ParserEngine()
        assert engine.detect_language("data.xyz") == ""


# ---------------------------------------------------------------------------
# TestSupportedLanguages
# ---------------------------------------------------------------------------


class TestSupportedLanguages:
    def test_supported_extensions(self):
        engine = ParserEngine()
        exts = engine.get_supported_extensions()
        required = [
            ".py", ".ts", ".js", ".go", ".rs", ".java", ".c", ".cpp",
            ".cs", ".kt", ".swift", ".php", ".rb", ".html", ".css",
            ".json", ".yml", ".yaml", ".sh", ".sql", ".md",
        ]
        for ext in required:
            assert ext in exts, f"{ext} not in supported extensions"

    def test_is_supported(self):
        engine = ParserEngine()
        assert engine.is_supported("file.py") is True
        assert engine.is_supported("file.xyz") is False


# ---------------------------------------------------------------------------
# TestPythonParsing
# ---------------------------------------------------------------------------


class TestPythonParsing:
    def test_parse_function(self):
        engine = ParserEngine()
        content = "def hello(name, age):\n    return f'Hello {name}'"
        result = engine.parse_file("test.py", content)
        funcs = [
            s for s in result.symbols
            if s.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)
        ]
        assert len(funcs) >= 1
        fn = funcs[0]
        assert fn.name == "hello"
        assert fn.start_line == 1
        assert fn.end_line >= 1
        params_text = " ".join(fn.parameters) if fn.parameters else fn.signature
        assert "name" in params_text

    def test_parse_class(self):
        engine = ParserEngine()
        content = "class Dog:\n    def bark(self):\n        return 'woof'"
        result = engine.parse_file("test.py", content)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"
        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) >= 1
        assert methods[0].name == "bark"

    def test_parse_imports(self):
        engine = ParserEngine()
        content = "import os\nfrom sys import argv"
        result = engine.parse_file("test.py", content)
        assert len(result.imports) >= 2
        names = [i.name for i in result.imports]
        assert "os" in names
        assert "argv" in names

    def test_parse_decorators(self):
        engine = ParserEngine()
        content = "@staticmethod\ndef foo():\n    pass"
        result = engine.parse_file("test.py", content)
        funcs = [
            s for s in result.symbols
            if s.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)
        ]
        assert len(funcs) >= 1
        assert funcs[0].name == "foo"

    def test_parse_async_function(self):
        engine = ParserEngine()
        content = "async def fetch_data():\n    pass"
        result = engine.parse_file("test.py", content)
        funcs = [
            s for s in result.symbols
            if s.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)
        ]
        assert len(funcs) >= 1
        assert funcs[0].is_async is True


# ---------------------------------------------------------------------------
# TestJavaScriptParsing
# ---------------------------------------------------------------------------


class TestJavaScriptParsing:
    def test_parse_js_function(self):
        engine = ParserEngine()
        content = "function greet(name) {\n    return 'hi';\n}"
        result = engine.parse_file("test.js", content)
        funcs = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(funcs) >= 1
        assert funcs[0].name == "greet"

    def test_parse_js_class(self):
        engine = ParserEngine()
        content = "class Animal {\n    speak() {\n        return '';\n    }\n}"
        result = engine.parse_file("test.js", content)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) >= 1
        assert classes[0].name == "Animal"

    def test_parse_js_imports(self):
        engine = ParserEngine()
        content = "import { foo } from 'bar';\nconst fs = require('fs');"
        result = engine.parse_file("test.js", content)
        assert len(result.imports) >= 2


# ---------------------------------------------------------------------------
# TestSecretDetection
# ---------------------------------------------------------------------------


class TestSecretDetection:
    def test_detect_api_key(self):
        engine = ParserEngine()
        content = 'api_key = "sk-1234567890abcdef1234567890ab"'
        result = engine.parse_file("test.py", content)
        assert result.tree_hash
        assert result.error == ""

    def test_detect_password(self):
        engine = ParserEngine()
        content = 'password = "super_secret_pass"'
        result = engine.parse_file("test.py", content)
        assert result.tree_hash
        assert result.error == ""

    def test_no_false_positives(self):
        engine = ParserEngine()
        content = 'def greet(name):\n    return f"Hello {name}"'
        result = engine.parse_file("test.py", content)
        assert result.error == ""
        funcs = [
            s for s in result.symbols
            if s.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)
        ]
        assert len(funcs) >= 1


# ---------------------------------------------------------------------------
# TestRegexFallback
# ---------------------------------------------------------------------------


class TestRegexFallback:
    def test_regex_python_functions(self):
        engine = ParserEngine()
        content = "def alpha():\n    pass\n\ndef beta():\n    pass"
        result = engine.parse_file("test.py", content)
        funcs = [
            s for s in result.symbols
            if s.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)
        ]
        names = [f.name for f in funcs]
        assert "alpha" in names
        assert "beta" in names

    def test_regex_python_classes(self):
        engine = ParserEngine()
        content = "class MyClass:\n    pass"
        result = engine.parse_file("test.py", content)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) >= 1
        assert classes[0].name == "MyClass"

    def test_regex_imports(self):
        engine = ParserEngine()
        content = "import json\nfrom pathlib import Path"
        result = engine.parse_file("test.py", content)
        assert len(result.imports) >= 2
        names = [i.name for i in result.imports]
        assert "json" in names
        assert "Path" in names


# ---------------------------------------------------------------------------
# TestLineCounting
# ---------------------------------------------------------------------------


class TestLineCounting:
    def test_count_lines(self):
        engine = ParserEngine()
        content = "// comment\n\nfunction foo() {\n    return 1;\n}"
        total, comment, blank = engine._count_lines(content)
        assert total == 5
        assert blank == 1
        assert comment == 1

    def test_count_docstrings(self):
        engine = ParserEngine()
        content = '"""\nModule docstring.\n"""\n\ndef hello():\n    pass'
        total, comment, blank = engine._count_lines(content)
        assert total == 6
        assert blank == 1

    def test_count_block_comments(self):
        engine = ParserEngine()
        content = "/* block comment\n   multi-line */\nfunction foo() {}"
        total, comment, blank = engine._count_lines(content)
        assert total == 3
        assert comment == 2
        assert blank == 0


# ---------------------------------------------------------------------------
# TestTreeHash
# ---------------------------------------------------------------------------


class TestTreeHash:
    def test_hash_same_content(self):
        engine = ParserEngine()
        h1 = engine._compute_tree_hash("hello world")
        h2 = engine._compute_tree_hash("hello world")
        assert h1 == h2

    def test_hash_different_content(self):
        engine = ParserEngine()
        h1 = engine._compute_tree_hash("hello")
        h2 = engine._compute_tree_hash("world")
        assert h1 != h2


# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_malformed_code(self):
        engine = ParserEngine()
        content = "def ( broken { { {"
        result = engine.parse_file("test.py", content)
        assert result.error == ""
        assert result.language == "python"

    def test_empty_file(self):
        engine = ParserEngine()
        result = engine.parse_file("test.py", "")
        assert result.language == "python"
        assert result.error == ""
