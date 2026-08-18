"""Tests for code smell detection at backend/app/code_intelligence/smells.py."""

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

from app.code_intelligence.smells import DEFAULT_CONFIG, SmellDetector  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────

_REPO_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_FILE_ID = "11111111-2222-3333-4444-555555555555"
_SYM_ID = "66666666-7777-8888-9999-aaaaaaaaaaaa"


def _make_detector(config: dict | None = None) -> SmellDetector:
    return SmellDetector(db_session=AsyncMock(), config=config)


def _mock_scalar_result(value: int):
    m = MagicMock()
    m.scalar.return_value = value
    return m


def _mock_result(rows):
    mock = MagicMock()
    mock.all.return_value = rows
    mock.scalars.return_value = mock
    mock.scalars().all.return_value = rows
    return mock


def _fake_symbol(name="fn", sym_type="METHOD", visibility="private", **overrides):
    sym = MagicMock()
    sym.name = name
    sym.symbol_type = sym_type
    sym.visibility = visibility
    sym.file_id = overrides.get("file_id", _FILE_ID)
    sym.id = overrides.get("id", _SYM_ID)
    sym.parent_symbol_id = overrides.get("parent_symbol_id", "MyClass")
    sym.start_line = overrides.get("start_line", 1)
    sym.end_line = overrides.get("end_line", 10)
    sym.parameters = overrides.get("parameters", None)
    for k, v in overrides.items():
        setattr(sym, k, v)
    return sym


def _fake_metrics(**overrides):
    m = MagicMock()
    m.function_length = overrides.get("function_length", 5)
    m.nesting_depth = overrides.get("nesting_depth", 2)
    m.loc = overrides.get("loc", 100)
    m.code_lines = overrides.get("code_lines", 80)
    m.comment_lines = overrides.get("comment_lines", 10)
    m.cyclomatic_complexity = overrides.get("cyclomatic_complexity", 3)
    m.fan_in = overrides.get("fan_in", 2)
    m.fan_out = overrides.get("fan_out", 3)
    m.symbol_id = overrides.get("symbol_id", None)
    m.file_id = overrides.get("file_id", _FILE_ID)
    m.repository_id = overrides.get("repository_id", _REPO_ID)
    return m


def _fake_file(path="src/main.py"):
    f = MagicMock()
    f.file_path = path
    f.file_name = path.rsplit("/", 1)[-1]
    f.id = _FILE_ID
    return f


def _fake_import(name="os", alias=None, resolved=True, external=False):
    imp = MagicMock()
    imp.imported_name = name
    imp.alias = alias
    imp.resolved = resolved
    imp.is_external = external
    imp.source_file_id = _FILE_ID
    imp.imported_symbol_id = None
    imp.repository_id = _REPO_ID
    return imp


def _fake_smell(smell_type="long_function", severity="low"):
    s = MagicMock()
    s.smell_type = smell_type
    s.severity = severity
    s.confidence = 0.8
    return s


# ─── Long Function ────────────────────────────────────────────────────


class TestLongFunction:
    @pytest.mark.asyncio
    async def test_detect_long_function(self):
        det = _make_detector()
        sym = _fake_symbol("process_data", function_length=100)
        met = _fake_metrics(function_length=100)
        file_ = _fake_file()

        det.db.execute = AsyncMock(return_value=_mock_result([(sym, met, file_)]))
        smell_mock = _fake_smell("long_function", "low")
        with patch.object(det, "_get_evidence", return_value="evidence"), \
             patch.object(det, "_create_smell", return_value=smell_mock) as mock_create:
            smells = await det.detect_long_functions(_REPO_ID)

        assert len(smells) == 1
        assert smells[0].smell_type == "long_function"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_smell_short_function(self):
        det = _make_detector()
        det.db.execute = AsyncMock(return_value=_mock_result([]))

        smells = await det.detect_long_functions(_REPO_ID)
        assert smells == []


# ─── God Class ────────────────────────────────────────────────────────


class TestGodClass:
    @pytest.mark.asyncio
    async def test_detect_god_class(self):
        det = _make_detector()
        class_sym = _fake_symbol("GodClass", sym_type="CLASS")
        file_ = _fake_file()

        god_class_row = (
            class_sym.id, class_sym.name, class_sym.file_id,
            class_sym.start_line, class_sym.end_line,
            file_.file_path, 30,
        )

        det.db.execute = AsyncMock(side_effect=[
            _mock_result([god_class_row]),
            _mock_scalar_result(30),
        ])

        smell_mock = _fake_smell("god_class", "high")
        with patch.object(det, "_get_evidence", return_value="evidence"), \
             patch.object(det, "_create_smell", return_value=smell_mock) as mock_create:
            smells = await det.detect_god_classes(_REPO_ID, threshold=5)

        assert len(smells) == 1
        assert smells[0].smell_type == "god_class"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_class_passes(self):
        det = _make_detector()
        det.db.execute = AsyncMock(return_value=_mock_result([]))

        smells = await det.detect_god_classes(_REPO_ID)
        assert smells == []


# ─── Deep Nesting ─────────────────────────────────────────────────────


class TestDeepNesting:
    @pytest.mark.asyncio
    async def test_detect_deep_nesting(self):
        det = _make_detector()
        sym = _fake_symbol("nested_fn")
        met = _fake_metrics(nesting_depth=8)
        file_ = _fake_file()

        det.db.execute = AsyncMock(return_value=_mock_result([(met, sym, file_)]))
        smell_mock = _fake_smell("deep_nesting", "low")
        with patch.object(det, "_get_evidence", return_value="evidence"), \
             patch.object(det, "_create_smell", return_value=smell_mock) as mock_create:
            smells = await det.detect_deep_nesting(_REPO_ID, threshold=5)

        assert len(smells) == 1
        assert smells[0].smell_type == "deep_nesting"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_shallow_code_passes(self):
        det = _make_detector()
        det.db.execute = AsyncMock(return_value=_mock_result([]))

        smells = await det.detect_deep_nesting(_REPO_ID)
        assert smells == []


# ─── Large Parameters ─────────────────────────────────────────────────


class TestLargeParameters:
    @pytest.mark.asyncio
    async def test_detect_large_param_list(self):
        det = _make_detector()
        params = ["a", "b", "c", "d", "e", "f", "g", "h"]
        sym = _fake_symbol("configure", parameters=params)
        file_ = _fake_file()

        det.db.execute = AsyncMock(return_value=_mock_result([(sym, file_)]))
        smell_mock = _fake_smell("large_parameter_list", "low")
        with patch.object(det, "_get_evidence", return_value="evidence"), \
             patch.object(det, "_create_smell", return_value=smell_mock) as mock_create:
            smells = await det.detect_large_parameter_lists(_REPO_ID, threshold=5)

        assert len(smells) == 1
        assert smells[0].smell_type == "large_parameter_list"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_few_params_passes(self):
        det = _make_detector()
        det.db.execute = AsyncMock(return_value=_mock_result([]))

        smells = await det.detect_large_parameter_lists(_REPO_ID)
        assert smells == []


# ─── Unused Imports ───────────────────────────────────────────────────


class TestUnusedImports:
    @pytest.mark.asyncio
    async def test_detect_unused_import(self):
        det = _make_detector()
        imp = _fake_import(name="unused_module", resolved=True)
        file_ = _fake_file()

        det.db.execute = AsyncMock(side_effect=[
            _mock_result([(imp, file_)]),
            _mock_scalar_result(0),
            _mock_scalar_result(0),
        ])

        smell_mock = _fake_smell("unused_import", "low")
        with patch.object(det, "_create_smell", return_value=smell_mock) as mock_create:
            smells = await det.detect_unused_imports(_REPO_ID)

        assert len(smells) == 1
        assert smells[0].smell_type == "unused_import"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_used_import_passes(self):
        det = _make_detector()
        imp = _fake_import(name="os", resolved=True)
        file_ = _fake_file()

        det.db.execute = AsyncMock(side_effect=[
            _mock_result([(imp, file_)]),
            _mock_scalar_result(5),
        ])

        smells = await det.detect_unused_imports(_REPO_ID)
        assert smells == []


# ─── Dead Code ────────────────────────────────────────────────────────


class TestDeadCode:
    @pytest.mark.asyncio
    async def test_detect_dead_code(self):
        det = _make_detector()
        sym = _fake_symbol("_internal_helper", visibility="private")
        file_ = _fake_file()

        det.db.execute = AsyncMock(side_effect=[
            _mock_result([(sym, file_)]),
            _mock_scalar_result(0),
            _mock_scalar_result(0),
        ])

        smell_mock = _fake_smell("dead_code", "low")
        with patch.object(det, "_get_evidence", return_value="evidence"), \
             patch.object(det, "_create_smell", return_value=smell_mock) as mock_create:
            smells = await det.detect_dead_code(_REPO_ID)

        assert len(smells) == 1
        assert smells[0].smell_type == "dead_code"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_used_code_passes(self):
        det = _make_detector()
        sym = _fake_symbol("active_fn", visibility="private")
        file_ = _fake_file()

        det.db.execute = AsyncMock(side_effect=[
            _mock_result([(sym, file_)]),
            _mock_scalar_result(3),
            _mock_scalar_result(1),
        ])

        smells = await det.detect_dead_code(_REPO_ID)
        assert smells == []


# ─── Smell Summary ────────────────────────────────────────────────────


class TestSmellSummary:
    @pytest.mark.asyncio
    async def test_summary_by_type(self):
        det = _make_detector()
        smells = [
            _fake_smell(smell_type="long_function", severity="low"),
            _fake_smell(smell_type="long_function", severity="medium"),
            _fake_smell(smell_type="god_class", severity="high"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_result
        mock_result.scalars().all.return_value = smells
        det.db.execute = AsyncMock(return_value=mock_result)

        summary = await det.get_smell_summary(_REPO_ID)
        assert summary["by_type"]["long_function"] == 2
        assert summary["by_type"]["god_class"] == 1

    @pytest.mark.asyncio
    async def test_summary_by_severity(self):
        det = _make_detector()
        smells = [
            _fake_smell(smell_type="a", severity="low"),
            _fake_smell(smell_type="b", severity="low"),
            _fake_smell(smell_type="c", severity="high"),
            _fake_smell(smell_type="d", severity="medium"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_result
        mock_result.scalars().all.return_value = smells
        det.db.execute = AsyncMock(return_value=mock_result)

        summary = await det.get_smell_summary(_REPO_ID)
        assert summary["by_severity"]["low"] == 2
        assert summary["by_severity"]["high"] == 1
        assert summary["by_severity"]["medium"] == 1
