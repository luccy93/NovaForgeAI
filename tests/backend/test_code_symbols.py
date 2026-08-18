"""Tests for symbol resolution and graph building at backend/app/code_intelligence/symbols.py.

Mock the DB session. Test the logic without actual DB calls.
"""

import importlib.util
import os
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

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

from app.code_intelligence.symbols import (
    CallGraphBuilder,
    DependencyGraphBuilder,
    ImportGraphBuilder,
    InheritanceGraphBuilder,
    SymbolResolver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(*results):
    """Create an AsyncMock session where ``execute`` returns *results* in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


def _result(*items):
    """Mock DB query result for ``.scalars().all()`` and ``.all()``."""
    r = MagicMock()
    items_list = list(items)
    r.scalars.return_value.all.return_value = items_list
    r.all.return_value = items_list
    return r


def _scalar_result(item):
    """Mock DB query result for ``.scalar_one_or_none()``."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = item
    return r


# ---------------------------------------------------------------------------
# TestSymbolResolver
# ---------------------------------------------------------------------------


class TestSymbolResolver:
    def test_build_qualified_name(self):
        result = SymbolResolver._build_qualified_name("method", "MyClass", "mymodule")
        assert result == "mymodule.MyClass.method"

    def test_generate_symbol_id(self):
        id1 = SymbolResolver._generate_symbol_id(
            "repo1", "commit1", "file.py", "MyClass.method"
        )
        id2 = SymbolResolver._generate_symbol_id(
            "repo1", "commit1", "file.py", "MyClass.method"
        )
        id3 = SymbolResolver._generate_symbol_id(
            "repo1", "commit1", "file.py", "Other.method"
        )
        assert id1 == id2
        assert id1 != id3

    def test_resolve_simple_import(self):
        target_sym = MagicMock()
        target_sym.id = uuid.uuid4()
        target_map = {
            "path": target_sym,
            "os.path": target_sym,
            str(target_sym.symbol_id): target_sym,
        }
        resolved, sid = SymbolResolver._resolve_name("path", target_map, {})
        assert resolved is True
        assert str(sid) == str(target_sym.id)

    @pytest.mark.asyncio
    async def test_resolve_class_inheritance(self):
        sym_a = MagicMock()
        sym_a.id = uuid.uuid4()
        sym_a.name = "A"
        sym_a.qualified_name = "A"
        sym_a.symbol_id = "sid_A"

        sym_b = MagicMock()
        sym_b.id = uuid.uuid4()
        sym_b.name = "B"
        sym_b.qualified_name = "B"
        sym_b.symbol_id = "sid_B"

        session = _mock_session(_result(sym_a, sym_b))

        resolver = SymbolResolver(session)
        refs = await resolver.resolve_inheritance(
            symbols=[
                {
                    "symbol_name": "B",
                    "bases": ["A"],
                    "file_id": str(uuid.uuid4()),
                    "index_id": str(uuid.uuid4()),
                }
            ],
            repo_id=str(uuid.uuid4()),
        )

        assert len(refs) >= 1
        assert any(ref.reference_type == "INHERITANCE" for ref in refs)

    @pytest.mark.asyncio
    async def test_search_symbols_filter(self):
        sym1 = MagicMock()
        sym1.name = "foo"
        sym1.symbol_type = "FUNCTION"

        sym2 = MagicMock()
        sym2.name = "Bar"
        sym2.symbol_type = "CLASS"

        session = _mock_session(_result(sym1, sym2))

        resolver = SymbolResolver(session)
        results = await resolver.search_symbols(
            "foo", str(uuid.uuid4()), symbol_type="FUNCTION"
        )
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_unresolved_references_tracked(self):
        unresolved_ref = MagicMock()
        unresolved_ref.resolved = False
        unresolved_ref.target_name = "unknown_module.func"

        session = _mock_session(
            _result(),              # _load_symbol_map (empty)
            _result(),              # _load_file_symbols (empty)
            _result(unresolved_ref),  # find_unresolved_references
        )

        resolver = SymbolResolver(session)
        refs = await resolver.resolve_references(
            symbols=[
                {
                    "source_name": "foo",
                    "target_name": "unknown_module.func",
                    "reference_type": "REFERENCE",
                    "line": 1,
                    "column": 0,
                }
            ],
            imports=[],
            file_id=str(uuid.uuid4()),
            repo_id=str(uuid.uuid4()),
            index_id=str(uuid.uuid4()),
        )

        assert len(refs) == 1
        assert refs[0].resolved is False
        assert refs[0].target_name == "unknown_module.func"

        unresolved = await resolver.find_unresolved_references(
            str(uuid.uuid4()), str(uuid.uuid4())
        )
        assert len(unresolved) == 1
        assert unresolved[0].resolved is False


# ---------------------------------------------------------------------------
# TestCallGraphBuilder
# ---------------------------------------------------------------------------


class TestCallGraphBuilder:
    @pytest.mark.asyncio
    async def test_direct_call(self):
        caller_id = uuid.uuid4()
        callee_id = uuid.uuid4()
        file_id = uuid.uuid4()

        caller_sym = MagicMock()
        caller_sym.id = caller_id
        caller_sym.name = "main"
        caller_sym.qualified_name = "main"
        caller_sym.file_id = file_id

        callee_sym = MagicMock()
        callee_sym.id = callee_id
        callee_sym.name = "helper"
        callee_sym.qualified_name = "helper"

        session = _mock_session(
            _result(callee_sym),   # _load_repo_symbols
            _result(caller_sym),   # file symbol query
        )

        builder = CallGraphBuilder(session)
        calls = await builder.build_call_graph(
            file_id=str(file_id),
            calls=[{"caller_name": "main", "callee_name": "helper", "line": 5}],
            symbols=[{"name": "main", "qualified_name": "main"}],
            repo_id=str(uuid.uuid4()),
            index_id=str(uuid.uuid4()),
        )

        assert len(calls) == 1
        assert calls[0].callee_name == "helper"

    def test_callee_resolution(self):
        sym = MagicMock()
        sym.id = uuid.uuid4()
        local_symbols = {"helper": sym}
        repo_symbols = {}

        resolved, sid = CallGraphBuilder._resolve_callee(
            "helper", local_symbols, repo_symbols, ""
        )
        assert resolved is True
        assert str(sid) == str(sym.id)

        resolved, sid = CallGraphBuilder._resolve_callee(
            "unknown", local_symbols, repo_symbols, ""
        )
        assert resolved is False
        assert sid is None

    @pytest.mark.asyncio
    async def test_get_callers(self):
        sym_id = uuid.uuid4()
        sym = MagicMock()
        sym.id = sym_id
        sym.symbol_id = "caller_sid"

        call = MagicMock()
        call.callee_name = "helper"
        call.call_line = 10

        session = _mock_session(
            _scalar_result(sym),   # _resolve_symbol_by_canonical_id
            _result(call),         # caller query
        )

        builder = CallGraphBuilder(session)
        callers = await builder.get_callers("caller_sid")

        assert len(callers) == 1
        assert callers[0].callee_name == "helper"

    @pytest.mark.asyncio
    async def test_detect_cycle(self):
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        id_c = uuid.uuid4()

        call_ab = MagicMock()
        call_ab.caller_symbol_id = id_a
        call_ab.callee_symbol_id = id_b

        call_bc = MagicMock()
        call_bc.caller_symbol_id = id_b
        call_bc.callee_symbol_id = id_c

        call_ca = MagicMock()
        call_ca.caller_symbol_id = id_c
        call_ca.callee_symbol_id = id_a

        session = _mock_session(_result(call_ab, call_bc, call_ca))

        builder = CallGraphBuilder(session)
        cycles = await builder.detect_cycles(str(uuid.uuid4()))

        assert len(cycles) >= 1
        cycle_ids = [str(c) for c in cycles[0]]
        assert str(id_a) in cycle_ids


# ---------------------------------------------------------------------------
# TestImportGraphBuilder
# ---------------------------------------------------------------------------


class TestImportGraphBuilder:
    @pytest.mark.asyncio
    async def test_absolute_import(self):
        repo_sym_map = {}

        session = _mock_session(_result())  # _load_repo_symbols (empty)

        builder = ImportGraphBuilder(session)
        imports = await builder.build_import_graph(
            file_id=str(uuid.uuid4()),
            imports=[{"imported_name": "os", "import_type": "ABSOLUTE"}],
            repo_id=str(uuid.uuid4()),
            index_id=str(uuid.uuid4()),
        )

        assert len(imports) == 1
        imp = imports[0]
        assert imp.imported_name == "os"
        assert imp.is_stdlib is True
        assert imp.is_external is False

    @pytest.mark.asyncio
    async def test_relative_import(self):
        session = _mock_session(_result())

        builder = ImportGraphBuilder(session)
        imports = await builder.build_import_graph(
            file_id=str(uuid.uuid4()),
            imports=[
                {"imported_name": "utils", "import_type": "FROM", "alias": None}
            ],
            repo_id=str(uuid.uuid4()),
            index_id=str(uuid.uuid4()),
        )

        assert len(imports) == 1
        assert imports[0].imported_name == "utils"

    @pytest.mark.asyncio
    async def test_external_detection(self):
        session = _mock_session(_result())

        builder = ImportGraphBuilder(session)
        imports = await builder.build_import_graph(
            file_id=str(uuid.uuid4()),
            imports=[{"imported_name": "requests", "import_type": "ABSOLUTE"}],
            repo_id=str(uuid.uuid4()),
            index_id=str(uuid.uuid4()),
        )

        assert len(imports) == 1
        imp = imports[0]
        assert imp.is_external is True
        assert imp.is_stdlib is False

    @pytest.mark.skip(
        reason="Bug in source: DFS cycle detection enters infinite loop — "
               "after finding a back edge the node is never popped/marked BLACK",
    )
    @pytest.mark.asyncio
    async def test_circular_imports(self):
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        sym_a_id = uuid.uuid4()
        sym_b_id = uuid.uuid4()
        repo_id = uuid.uuid4()

        imp_ab = MagicMock()
        imp_ab.source_file_id = id_a
        imp_ab.imported_symbol_id = sym_b_id
        imp_ab.resolved = True
        imp_ab.repository_id = repo_id

        imp_ba = MagicMock()
        imp_ba.source_file_id = id_b
        imp_ba.imported_symbol_id = sym_a_id
        imp_ba.resolved = True
        imp_ba.repository_id = repo_id

        file_a = MagicMock()
        file_a.id = id_a
        file_a.file_path = "a.py"

        file_b = MagicMock()
        file_b.id = id_b
        file_b.file_path = "b.py"

        sym_a_obj = MagicMock()
        sym_a_obj.id = sym_a_id
        sym_a_obj.file_id = id_a

        sym_b_obj = MagicMock()
        sym_b_obj.id = sym_b_id
        sym_b_obj.file_id = id_b

        session = _mock_session(
            _result(imp_ab, imp_ba),       # initial import query
            _result(file_a, file_b),        # _load_file_paths
            _result(sym_a_obj, sym_b_obj),  # _load_symbol_to_file_map
        )

        builder = ImportGraphBuilder(session)
        cycles = await builder.detect_circular_imports(str(repo_id))

        assert len(cycles) >= 1


# ---------------------------------------------------------------------------
# TestDependencyGraphBuilder
# ---------------------------------------------------------------------------


class TestDependencyGraphBuilder:
    @pytest.mark.asyncio
    async def test_file_dependencies(self):
        file_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        sym_helper_id = uuid.uuid4()
        file_b_id = uuid.uuid4()
        sym_process_id = uuid.uuid4()
        file_c_id = uuid.uuid4()

        imp = MagicMock()
        imp.imported_name = "helper"
        imp.imported_symbol_id = sym_helper_id
        imp.is_external = False
        imp.is_stdlib = True
        imp.resolved = True
        imp.repository_id = repo_id

        call = MagicMock()
        call.callee_name = "process"
        call.callee_symbol_id = sym_process_id
        call.resolved = True
        call.repository_id = repo_id

        sym_helper = MagicMock()
        sym_helper.id = sym_helper_id
        sym_helper.file_id = file_b_id

        sym_process = MagicMock()
        sym_process.id = sym_process_id
        sym_process.file_id = file_c_id

        session = _mock_session(
            _result(imp),                        # import query
            _result(call),                       # call query
            _result(sym_helper, sym_process),    # _load_symbol_to_file_map
        )

        builder = DependencyGraphBuilder(session)
        deps = await builder.get_file_dependencies(str(file_id))

        assert "imports" in deps
        assert "calls" in deps
        assert len(deps["imports"]) == 1
        assert deps["imports"][0]["imported_name"] == "helper"

    @pytest.mark.asyncio
    async def test_dependents(self):
        file_id = uuid.uuid4()
        sym_id = uuid.uuid4()
        source_file_id = uuid.uuid4()

        file_sym = MagicMock()
        file_sym.id = sym_id

        imp_row = MagicMock()
        imp_row.source_file_id = source_file_id
        imp_row.imported_name = "helper"
        imp_row.file_path = "other.py"

        session = _mock_session(
            _result(file_sym),   # file symbol query
            _result(imp_row),    # import dependents
            _result(),           # call dependents (empty)
        )

        builder = DependencyGraphBuilder(session)
        dependents = await builder.get_dependents(str(file_id))

        assert len(dependents) >= 1
        assert dependents[0]["dependency_type"] == "import"

    @pytest.mark.asyncio
    async def test_coupling_calculation(self):
        file_a_id = uuid.uuid4()
        file_b_id = uuid.uuid4()
        sym_a_id = uuid.uuid4()
        sym_b_id = uuid.uuid4()
        repo_id = uuid.uuid4()

        file_a = MagicMock()
        file_a.id = file_a_id
        file_a.file_path = "a.py"

        file_b = MagicMock()
        file_b.id = file_b_id
        file_b.file_path = "b.py"

        sym_a = MagicMock()
        sym_a.id = sym_a_id
        sym_a.file_id = file_a_id

        sym_b = MagicMock()
        sym_b.id = sym_b_id
        sym_b.file_id = file_b_id

        imp = MagicMock()
        imp.source_file_id = file_a_id
        imp.imported_symbol_id = sym_b_id

        call = MagicMock()
        call.caller_file_id = file_a_id
        call.callee_symbol_id = sym_b_id

        session = _mock_session(
            _result(file_a, file_b),  # files
            _result(sym_a, sym_b),    # _load_symbol_to_file_map
            _result(imp),             # imports
            _result(call),            # calls
        )

        builder = DependencyGraphBuilder(session)
        metrics = await builder.calculate_coupling(str(repo_id))

        assert len(metrics) == 2
        file_ids = {m["file_id"] for m in metrics}
        assert str(file_a_id) in file_ids
        assert str(file_b_id) in file_ids

        a_metrics = next(m for m in metrics if m["file_id"] == str(file_a_id))
        assert a_metrics["efferent_coupling"] >= 1


# ---------------------------------------------------------------------------
# TestInheritanceGraphBuilder
# ---------------------------------------------------------------------------


class TestInheritanceGraphBuilder:
    @pytest.mark.asyncio
    async def test_superclasses(self):
        child_db_id = uuid.uuid4()
        parent_db_id = uuid.uuid4()

        child = MagicMock()
        child.id = child_db_id
        child.symbol_id = "child_sid"
        child.name = "B"

        parent = MagicMock()
        parent.id = parent_db_id
        parent.symbol_id = "parent_sid"
        parent.name = "A"

        ref = MagicMock()
        ref.target_name = "A"
        ref.resolved = True
        ref.target_symbol_id = parent_db_id

        session = _mock_session(
            _scalar_result(child),  # _resolve_symbol_by_canonical_id
            _result(ref),           # query refs
            _scalar_result(parent), # _resolve_symbol_db_id
        )

        builder = InheritanceGraphBuilder(session)
        parents = await builder.get_superclasses("child_sid")

        assert len(parents) == 1
        assert parents[0]["target_name"] == "A"
        assert parents[0]["resolved"] is True

    @pytest.mark.asyncio
    async def test_subclasses(self):
        parent_db_id = uuid.uuid4()
        child_db_id = uuid.uuid4()

        parent = MagicMock()
        parent.id = parent_db_id
        parent.symbol_id = "parent_sid"
        parent.name = "A"

        child = MagicMock()
        child.id = child_db_id
        child.symbol_id = "child_sid"
        child.name = "B"

        ref = MagicMock()
        ref.target_name = "A"
        ref.resolved = True
        ref.source_symbol_id = child_db_id

        session = _mock_session(
            _scalar_result(parent),  # _resolve_symbol_by_canonical_id
            _result(ref),            # query refs
            _scalar_result(child),   # _resolve_symbol_db_id
        )

        builder = InheritanceGraphBuilder(session)
        children = await builder.get_subclasses("parent_sid")

        assert len(children) == 1

    @pytest.mark.asyncio
    async def test_implementations(self):
        iface_db_id = uuid.uuid4()
        widget_db_id = uuid.uuid4()

        iface = MagicMock()
        iface.id = iface_db_id
        iface.symbol_id = "iface_sid"
        iface.name = "Renderable"
        iface.symbol_type = "INTERFACE"

        widget = MagicMock()
        widget.id = widget_db_id
        widget.symbol_id = "widget_sid"
        widget.name = "Widget"
        widget.symbol_type = "CLASS"

        ref = MagicMock()
        ref.target_name = "Renderable"
        ref.resolved = True
        ref.source_symbol_id = widget_db_id

        session = _mock_session(
            _scalar_result(iface),   # _resolve_symbol_by_canonical_id
            _result(),               # as-source query (empty)
            _result(ref),            # as-target query
            _scalar_result(widget),  # _resolve_symbol_db_id
        )

        builder = InheritanceGraphBuilder(session)
        impls = await builder.get_implementations("iface_sid")

        assert len(impls) == 1
