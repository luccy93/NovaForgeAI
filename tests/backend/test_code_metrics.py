"""Tests for code metrics calculator at backend/app/code_intelligence/metrics.py."""

import math
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Prevent app/__init__.py from triggering the broken API import chain.
_APP_DIR = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "backend" / "app")
if "app" not in sys.modules:
    _stub = types.ModuleType("app")
    _stub.__path__ = [_APP_DIR]
    sys.modules["app"] = _stub

if "app.api" not in sys.modules:
    sys.modules["app.api"] = types.ModuleType("app.api")

from app.code_intelligence.metrics import MetricsCalculator  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────


def _make_calc() -> MetricsCalculator:
    return MetricsCalculator(db_session=AsyncMock())


# ─── Line Counting ────────────────────────────────────────────────────


class TestLineCounting:
    def test_count_loc_python(self):
        calc = _make_calc()
        content = (
            "# this is a comment\n"
            "def foo():\n"
            "    return 1\n"
            "\n"
        )
        result = calc._count_loc(content)
        assert result["loc"] == 4
        assert result["code_lines"] == 2
        assert result["comment_lines"] == 1
        assert result["blank_lines"] == 1

    def test_count_loc_javascript(self):
        calc = _make_calc()
        content = (
            "// top comment\n"
            "function bar() {\n"
            "    return 42;\n"
            "}\n"
            "/* block\n"
            "   comment */\n"
            "\n"
        )
        result = calc._count_loc(content)
        assert result["loc"] == 7
        assert result["code_lines"] == 3
        assert result["comment_lines"] == 3
        assert result["blank_lines"] == 1

    def test_mixed_content(self):
        calc = _make_calc()
        content = (
            "# header\n"
            "x = 1\n"
            "/* multi\n"
            "line */\n"
            "y = 2\n"
            "\n"
            "z = x + y\n"
        )
        result = calc._count_loc(content)
        assert result["loc"] == 7
        assert result["blank_lines"] == 1
        assert result["comment_lines"] >= 1
        assert result["code_lines"] >= 2


# ─── Complexity ────────────────────────────────────────────────────────


class TestComplexity:
    def test_cyclomatic_simple_function(self):
        calc = _make_calc()
        content = (
            "def simple():\n"
            "    x = 1\n"
            "    return x\n"
        )
        cc = calc._cyclomatic_complexity(content, "python")
        assert cc == 1

    def test_cyclomatic_complex_function(self):
        calc = _make_calc()
        content = (
            "def complex(x):\n"
            "    if x > 0:\n"
            "        for i in range(x):\n"
            "            if i % 2 == 0:\n"
            "                while i > 10:\n"
            "                    pass\n"
            "    elif x < 0:\n"
            "        pass\n"
            "    else:\n"
            "        pass\n"
        )
        cc = calc._cyclomatic_complexity(content, "python")
        assert cc >= 5

    def test_cognitive_complexity(self):
        calc = _make_calc()
        content = (
            "def nested():\n"
            "    if True:\n"
            "        for i in range(10):\n"
            "            if i > 5:\n"
            "                return i\n"
        )
        cog = calc._cognitive_complexity(content, "python")
        assert cog > 0

    def test_nesting_depth(self):
        calc = _make_calc()
        flat = "x = 1;\ny = 2;\n"
        deep = (
            "if (a) {\n"
            "  if (b) {\n"
            "    if (c) {\n"
            "      if (d) {\n"
            "        x = 1;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        assert calc._nesting_depth(flat, "c") < calc._nesting_depth(deep, "c")


# ─── Halstead ─────────────────────────────────────────────────────────


class TestHalstead:
    def test_halstead_volume(self):
        calc = _make_calc()
        content = "x = a + b * c\n"
        vol = calc._halstead_volume(content)
        assert isinstance(vol, float)
        assert vol > 0

    def test_halstead_simple(self):
        calc = _make_calc()
        simple = "return 0\n"
        complex_ = "result = alpha + beta * gamma - delta / epsilon\n"
        assert calc._halstead_volume(simple) < calc._halstead_volume(complex_)


# ─── Maintainability ──────────────────────────────────────────────────


class TestMaintainability:
    def test_maintainability_index(self):
        calc = _make_calc()
        mi = calc._maintainability_index(loc=100, cc=5, halstead=500.0)
        assert isinstance(mi, float)
        assert 0.0 <= mi <= 100.0

    def test_maintainability_low(self):
        calc = _make_calc()
        mi_good = calc._maintainability_index(loc=50, cc=2, halstead=100.0)
        mi_bad = calc._maintainability_index(loc=1000, cc=50, halstead=10000.0)
        assert mi_bad < mi_good


# ─── Parameter Count ──────────────────────────────────────────────────


class TestParameterCount:
    def test_params_python(self):
        calc = _make_calc()
        content = "def foo(a, b, c, d, e):\n    pass\n"
        assert calc._parameter_count(content, "python") == 5

    def test_params_zero(self):
        calc = _make_calc()
        content = "def bar():\n    pass\n"
        assert calc._parameter_count(content, "python") == 0


# ─── Fan-in / Fan-out ─────────────────────────────────────────────────


class TestFanInOut:
    @pytest.mark.asyncio
    async def test_fan_in(self):
        calc = _make_calc()
        mock_scalar = MagicMock()
        mock_scalar.scalar.return_value = 3
        calc.db.execute = AsyncMock(return_value=mock_scalar)

        fan_in, fan_out = await calc._fan_in_fan_out(
            "00000000-0000-0000-0000-000000000001"
        )
        assert fan_in == 3

    @pytest.mark.asyncio
    async def test_fan_out(self):
        calc = _make_calc()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.scalar.return_value = call_count * 2
            return mock_result

        calc.db.execute = AsyncMock(side_effect=side_effect)
        fan_in, fan_out = await calc._fan_in_fan_out(
            "00000000-0000-0000-0000-000000000001"
        )
        assert fan_out == 2
