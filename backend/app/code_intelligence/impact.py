"""Impact Analysis and Refactoring Intelligence Engine.

Provides blast-radius estimation, dependency graph traversal, breaking-change
detection, rename/move impact analysis, dead-code detection, and change-risk
scoring for refactoring planning.
"""

import logging
import math
import uuid as _uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeCall,
    CodeFile,
    CodeHistory,
    CodeImport,
    CodeReference,
    CodeSymbol,
    ReferenceType,
)

logger = logging.getLogger(__name__)

# ── Risk thresholds ───────────────────────────────────────────────────

RISK_LOW = 0.3
RISK_MEDIUM = 0.6
RISK_HIGH = 0.85


# ── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class ImpactResult:
    """Full impact analysis result for a symbol or file."""

    target_id: str = ""
    target_type: str = "symbol"  # "symbol" | "file"
    target_name: str = ""
    dependents: list[dict] = field(default_factory=list)
    transitive_dependents: list[dict] = field(default_factory=list)
    dependencies: list[dict] = field(default_factory=list)
    transitive_dependencies: list[dict] = field(default_factory=list)
    callers: list[dict] = field(default_factory=list)
    callees: list[dict] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    documentation: list[dict] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)
    workflows: list[dict] = field(default_factory=list)
    affected_files: int = 0
    affected_symbols: int = 0
    affected_layers: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    risk_level: str = "LOW"
    blast_radius: int = 0
    confidence: float = 1.0


@dataclass
class ChangeScope:
    """Estimated scope of a multi-symbol change."""

    changed_symbols: list[str] = field(default_factory=list)
    affected_symbols: int = 0
    affected_files: int = 0
    affected_layers: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    risk_level: str = "LOW"
    affected_tests: list[str] = field(default_factory=list)
    affected_docs: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    estimated_effort: str = "small"


@dataclass
class RenameImpact:
    """Impact assessment for renaming a symbol."""

    symbol_id: str = ""
    old_name: str = ""
    new_name: str = ""
    files_to_modify: list[str] = field(default_factory=list)
    references_to_update: int = 0
    breaking_changes: list[dict] = field(default_factory=list)
    risk_score: float = 0.0
    auto_fixable: bool = True
    affected_tests: list[str] = field(default_factory=list)


@dataclass
class MoveImpact:
    """Impact assessment for moving a symbol to a new file."""

    symbol_id: str = ""
    old_file: str = ""
    new_file: str = ""
    imports_to_update: list[dict] = field(default_factory=list)
    references_to_update: int = 0
    breaking_changes: list[dict] = field(default_factory=list)
    risk_score: float = 0.0
    auto_fixable: bool = True


# ── Layer classification heuristics ───────────────────────────────────

_LAYER_PATTERNS: dict[str, list[str]] = {
    "presentation": [
        "component", "view", "page", "screen", "template", "layout",
        "widget", "ui", "frontend",
    ],
    "business_logic": [
        "service", "handler", "usecase", "interactor", "manager",
        "facade", "orchestrator", "domain", "business", "core", "logic",
    ],
    "data_access": [
        "repository", "dao", "dal", "model", "entity", "schema",
        "migration", "database", "db", "orm", "store", "gateway",
    ],
    "infrastructure": [
        "config", "middleware", "logging", "auth", "cache", "queue",
        "worker", "infrastructure", "infra", "celery",
    ],
    "test": [
        "test", "spec", "mock", "fixture", "conftest",
    ],
}


def _classify_layer(file_path: str, symbol_name: str) -> str:
    """Heuristically classify a file/symbol into an architectural layer."""
    combined = f"{file_path} {symbol_name}".lower()
    best_layer = "unknown"
    best_score = 0
    for layer_name, keywords in _LAYER_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score = score
            best_layer = layer_name
    return best_layer


def _risk_level(score: float) -> str:
    """Map a 0-1 risk score to a human-readable level."""
    if score < RISK_LOW:
        return "LOW"
    if score < RISK_MEDIUM:
        return "MEDIUM"
    if score < RISK_HIGH:
        return "HIGH"
    return "CRITICAL"


# ── ImpactAnalyzer ────────────────────────────────────────────────────


class ImpactAnalyzer:
    """Blast-radius and refactoring impact analysis engine.

    Walks the code-intelligence knowledge graph (references, calls, imports,
    tests, documentation, API endpoints, workflows) to produce structured
    impact assessments.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    # ── public: full symbol impact ────────────────────────────────────

    async def analyze_impact(self, symbol_id: str) -> ImpactResult:
        """Run full impact analysis for a single symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return ImpactResult(
                target_id=symbol_id,
                target_type="symbol",
                target_name=symbol_id,
                confidence=0.0,
            )

        dependents = await self.get_dependents(symbol_id)
        transitive = await self.get_dependents(symbol_id, depth=5)
        dependencies = await self.get_dependencies(symbol_id)
        transitive_deps = await self.get_dependencies(symbol_id, depth=5)
        callers = await self.get_callers(symbol_id)
        callees = await self.get_callees(symbol_id)
        tests = await self.get_tests_for_symbol(symbol_id)
        docs = await self.get_related_documentation(symbol_id)
        api_endpoints = await self.get_related_api(symbol_id)
        workflows = await self.get_affected_workflows(symbol_id)

        affected_file_ids: set[str] = set()
        affected_sym_ids: set[str] = set()
        layers: set[str] = set()

        for item in dependents:
            fid = item.get("file_id", "")
            if fid:
                affected_file_ids.add(fid)
            sid = item.get("symbol_id", "")
            if sid:
                affected_sym_ids.add(sid)
            layers.add(item.get("layer", "unknown"))

        for item in transitive:
            sid = item.get("symbol_id", "")
            if sid:
                affected_sym_ids.add(sid)
            fid = item.get("file_id", "")
            if fid:
                affected_file_ids.add(fid)

        for item in callers:
            sid = item.get("symbol_id", "")
            if sid:
                affected_sym_ids.add(sid)
            fid = item.get("file_id", "")
            if fid:
                affected_file_ids.add(fid)

        for item in tests:
            sid = item.get("symbol_id", "")
            if sid:
                affected_sym_ids.add(sid)

        result = ImpactResult(
            target_id=symbol_id,
            target_type="symbol",
            target_name=symbol.name,
            dependents=dependents,
            transitive_dependents=transitive,
            dependencies=dependencies,
            transitive_dependencies=transitive_deps,
            callers=callers,
            callees=callees,
            tests=tests,
            documentation=docs,
            api_endpoints=api_endpoints,
            workflows=workflows,
            affected_files=len(affected_file_ids),
            affected_symbols=len(affected_sym_ids),
            affected_layers=sorted(layers),
        )

        result.risk_score = self._calculate_risk_score(result)
        result.risk_level = _risk_level(result.risk_score)
        result.blast_radius = (
            len(dependents)
            + len(transitive)
            + len(callers)
            + len(tests)
            + len(api_endpoints)
        )

        return result

    # ── public: full file impact ──────────────────────────────────────

    async def analyze_file_impact(self, file_id: str) -> ImpactResult:
        """Run full impact analysis for all symbols in a file."""
        file_row = await self._resolve_file(file_id)
        if file_row is None:
            return ImpactResult(
                target_id=file_id,
                target_type="file",
                target_name=file_id,
                confidence=0.0,
            )

        symbols_stmt = select(CodeSymbol).where(CodeSymbol.file_id == file_id)
        symbols_result = await self._db.execute(symbols_stmt)
        symbols = list(symbols_result.scalars().all())

        all_dependents: list[dict] = []
        all_transitive: list[dict] = []
        all_callers: list[dict] = []
        all_callees: list[dict] = []
        all_tests: list[dict] = []
        all_docs: list[dict] = []
        all_api: list[dict] = []
        all_workflows: list[dict] = []
        affected_sym_ids: set[str] = set()
        affected_file_ids: set[str] = set()
        layers: set[str] = set()

        for sym in symbols:
            sid = sym.symbol_id
            deps = await self.get_dependents(sid)
            trans = await self.get_dependents(sid, depth=3)
            callr = await self.get_callers(sid)
            calle = await self.get_callees(sid)
            tsts = await self.get_tests_for_symbol(sid)
            dcs = await self.get_related_documentation(sid)
            apis = await self.get_related_api(sid)
            wfs = await self.get_affected_workflows(sid)

            all_dependents.extend(deps)
            all_transitive.extend(trans)
            all_callers.extend(callr)
            all_callees.extend(calle)
            all_tests.extend(tsts)
            all_docs.extend(dcs)
            all_api.extend(apis)
            all_workflows.extend(wfs)

            layer = _classify_layer(file_row.file_path, sym.name)
            layers.add(layer)

        for item in all_dependents + all_transitive + all_callers:
            fid = item.get("file_id", "")
            if fid:
                affected_file_ids.add(fid)
            sid = item.get("symbol_id", "")
            if sid:
                affected_sym_ids.add(sid)

        result = ImpactResult(
            target_id=file_id,
            target_type="file",
            target_name=file_row.file_path,
            dependents=all_dependents,
            transitive_dependents=all_transitive,
            dependencies=await self._get_file_dependencies(file_id),
            transitive_dependencies=[],
            callers=all_callers,
            callees=all_callees,
            tests=all_tests,
            documentation=all_docs,
            api_endpoints=all_api,
            workflows=all_workflows,
            affected_files=len(affected_file_ids),
            affected_symbols=len(affected_sym_ids) + len(symbols),
            affected_layers=sorted(layers),
        )

        result.risk_score = self._calculate_risk_score(result)
        result.risk_level = _risk_level(result.risk_score)
        result.blast_radius = (
            len(all_dependents)
            + len(all_transitive)
            + len(all_callers)
            + len(all_tests)
            + len(all_api)
        )

        return result

    # ── public: dependents / dependencies ─────────────────────────────

    async def get_dependents(
        self, symbol_id: str, depth: int = 3
    ) -> list[dict]:
        """Find all things that depend on *symbol_id* (direct and transitive).

        Walks import, reference, and call edges upstream.
        """
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        return await self._traverse_graph(
            start_id=symbol.symbol_id,
            direction="upstream",
            edge_types=[
                ReferenceType.IMPORT.value,
                ReferenceType.REFERENCE.value,
                ReferenceType.CALL.value,
                ReferenceType.INHERITANCE.value,
                ReferenceType.IMPLEMENTATION.value,
            ],
            max_depth=depth,
        )

    async def get_dependencies(
        self, symbol_id: str, depth: int = 3
    ) -> list[dict]:
        """Find all things *symbol_id* depends on (direct and transitive).

        Walks import, reference, and call edges downstream.
        """
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        return await self._traverse_graph(
            start_id=symbol.symbol_id,
            direction="downstream",
            edge_types=[
                ReferenceType.IMPORT.value,
                ReferenceType.REFERENCE.value,
                ReferenceType.CALL.value,
                ReferenceType.INHERITANCE.value,
                ReferenceType.IMPLEMENTATION.value,
            ],
            max_depth=depth,
        )

    # ── public: callers / callees ─────────────────────────────────────

    async def get_callers(self, symbol_id: str) -> list[dict]:
        """Return direct callers of a symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        stmt = (
            select(CodeCall)
            .where(CodeCall.callee_symbol_id == symbol.id)
            .order_by(CodeCall.call_line)
        )
        result = await self._db.execute(stmt)
        calls = result.scalars().all()

        callers: list[dict] = []
        seen_ids: set[str] = set()
        for call in calls:
            caller_sym = await self._resolve_symbol_db_id(call.caller_symbol_id)
            if caller_sym is None:
                continue
            if caller_sym.symbol_id in seen_ids:
                continue
            seen_ids.add(caller_sym.symbol_id)
            callers.append({
                "symbol_id": caller_sym.symbol_id,
                "name": caller_sym.name,
                "qualified_name": caller_sym.qualified_name,
                "symbol_type": caller_sym.symbol_type,
                "file_id": str(caller_sym.file_id),
                "call_line": call.call_line,
                "call_type": call.call_type,
                "resolved": call.resolved,
                "confidence": call.confidence,
                "layer": _classify_layer("", caller_sym.name),
            })

        return callers

    async def get_callees(self, symbol_id: str) -> list[dict]:
        """Return direct callees of a symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        stmt = (
            select(CodeCall)
            .where(CodeCall.caller_symbol_id == symbol.id)
            .order_by(CodeCall.call_line)
        )
        result = await self._db.execute(stmt)
        calls = result.scalars().all()

        callees: list[dict] = []
        seen_ids: set[str] = set()
        for call in calls:
            callee_sym = await self._resolve_symbol_db_id(call.callee_symbol_id)
            name = callee_sym.name if callee_sym else call.callee_name
            qualified = callee_sym.qualified_name if callee_sym else call.callee_name
            sid = callee_sym.symbol_id if callee_sym else call.callee_name
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            callees.append({
                "symbol_id": sid,
                "name": name,
                "qualified_name": qualified,
                "symbol_type": callee_sym.symbol_type if callee_sym else "unknown",
                "file_id": str(callee_sym.file_id) if callee_sym else "",
                "call_line": call.call_line,
                "call_type": call.call_type,
                "resolved": call.resolved,
                "confidence": call.confidence,
                "layer": _classify_layer("", name),
            })

        return callees

    # ── public: tests ─────────────────────────────────────────────────

    async def get_tests_for_symbol(self, symbol_id: str) -> list[dict]:
        """Find tests that cover or reference a symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        from app.code_intelligence.models import CodeTest

        # Match by source_symbol_name
        stmt = (
            select(CodeTest)
            .where(
                CodeTest.repository_id == symbol.repository_id,
                CodeTest.source_symbol_name == symbol.name,
            )
        )
        result = await self._db.execute(stmt)
        tests = result.scalars().all()

        found: list[dict] = []
        seen: set[str] = set()
        for test in tests:
            key = test.test_name
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "test_name": test.test_name,
                "test_type": test.test_type,
                "file_id": str(test.file_id),
                "source_symbol_name": test.source_symbol_name,
                "source_file_path": test.source_file_path,
                "framework": test.framework,
                "is_async": test.is_async,
            })

        # Also check if any test file imports this symbol
        import_stmt = (
            select(CodeImport)
            .where(
                CodeImport.imported_symbol_id == symbol.id,
            )
        )
        import_result = await self._db.execute(import_stmt)
        imports = import_result.scalars().all()
        for imp in imports:
            file_row = await self._resolve_file(str(imp.source_file_id))
            if file_row and file_row.is_test_file:
                test_key = f"file:{file_row.file_path}"
                if test_key not in seen:
                    seen.add(test_key)
                    found.append({
                        "test_name": file_row.file_name,
                        "test_type": "FILE",
                        "file_id": str(file_row.id),
                        "source_symbol_name": symbol.name,
                        "source_file_path": file_row.file_path,
                        "framework": None,
                        "is_async": False,
                    })

        return found

    async def get_tests_for_file(self, file_id: str) -> list[dict]:
        """Find tests that cover symbols in a file."""
        from app.code_intelligence.models import CodeTest

        file_row = await self._resolve_file(file_id)
        if file_row is None:
            return []

        symbols_stmt = select(CodeSymbol).where(CodeSymbol.file_id == file_id)
        symbols_result = await self._db.execute(symbols_stmt)
        symbols = list(symbols_result.scalars().all())

        all_tests: list[dict] = []
        seen: set[str] = set()

        for sym in symbols:
            sym_tests = await self.get_tests_for_symbol(sym.symbol_id)
            for t in sym_tests:
                key = t["test_name"]
                if key not in seen:
                    seen.add(key)
                    all_tests.append(t)

        return all_tests

    # ── public: documentation ─────────────────────────────────────────

    async def get_related_documentation(self, symbol_id: str) -> list[dict]:
        """Find documentation files that mention this symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        doc_files_stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == symbol.repository_id,
                CodeFile.is_documentation.is_(True),
            )
        )
        doc_result = await self._db.execute(doc_files_stmt)
        doc_files = doc_result.scalars().all()

        found: list[dict] = []
        symbol_name = symbol.name
        qualified = symbol.qualified_name

        for doc_file in doc_files:
            chunks_stmt = (
                select(CodeSymbol)
                .where(
                    CodeSymbol.file_id == doc_file.id,
                )
            )
            chunks_result = await self._db.execute(chunks_stmt)
            chunks = chunks_result.scalars().all()

            # Check if any symbol in the doc file references our symbol
            ref_stmt = (
                select(CodeReference)
                .where(
                    CodeReference.source_file_id == doc_file.id,
                    CodeReference.target_symbol_id == symbol.id,
                )
            )
            ref_result = await self._db.execute(ref_stmt)
            refs = ref_result.scalars().all()
            if refs:
                found.append({
                    "file_path": doc_file.file_path,
                    "file_id": str(doc_file.id),
                    "reference_count": len(refs),
                    "match_type": "reference",
                })
                continue

            # Fallback: check if symbol name appears in doc symbol names
            for chunk in chunks:
                if symbol_name in chunk.name or symbol_name in (chunk.qualified_name or ""):
                    found.append({
                        "file_path": doc_file.file_path,
                        "file_id": str(doc_file.id),
                        "reference_count": 1,
                        "match_type": "name_mention",
                    })
                    break

        return found

    # ── public: API endpoints ─────────────────────────────────────────

    async def get_related_api(self, symbol_id: str) -> list[dict]:
        """Find API endpoint functions that use this symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        # Find callers that are likely API endpoints (have route decorators)
        callers = await self.get_callers(symbol_id)
        api_endpoints: list[dict] = []

        for caller in callers:
            caller_sym = await self._resolve_symbol(caller["symbol_id"])
            if caller_sym is None:
                continue

            # Check decorators for route patterns
            decorators = caller_sym.decorators or []
            has_route_decorator = False
            route = ""
            method = "ANY"

            for dec in decorators if isinstance(decorators, list) else []:
                if isinstance(dec, str):
                    dec_lower = dec.lower()
                    if any(
                        m in dec_lower
                        for m in ("get", "post", "put", "delete", "patch", "route")
                    ):
                        has_route_decorator = True
                        route = dec
                        for http_m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                            if http_m.lower() in dec_lower:
                                method = http_m
                                break
                elif isinstance(dec, dict):
                    dec_str = str(dec).lower()
                    if any(
                        m in dec_str
                        for m in ("get", "post", "put", "delete", "patch", "route")
                    ):
                        has_route_decorator = True
                        route = dec.get("name", str(dec))
                        for http_m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                            if http_m.lower() in dec_str:
                                method = http_m
                                break

            if has_route_decorator:
                file_row = await self._resolve_file(str(caller_sym.file_id))
                api_endpoints.append({
                    "symbol_id": caller_sym.symbol_id,
                    "name": caller_sym.name,
                    "route": route,
                    "method": method,
                    "file_path": file_row.file_path if file_row else "",
                    "file_id": str(caller_sym.file_id),
                    "via": "direct_caller",
                })

        # Also check if this symbol is defined in a file with API endpoints
        symbol_file = await self._resolve_file(str(symbol.file_id))
        if symbol_file:
            file_refs_stmt = (
                select(CodeReference)
                .where(
                    CodeReference.source_file_id == symbol.id,
                    CodeReference.reference_type == ReferenceType.CALL.value,
                )
            )
            # Symbol itself might be an endpoint handler
            if symbol.symbol_type in ("FUNCTION", "METHOD"):
                for dec in (symbol.decorators or []) if isinstance(symbol.decorators, list) else []:
                    dec_str = str(dec).lower() if dec else ""
                    if any(m in dec_str for m in ("get", "post", "put", "delete", "patch", "route")):
                        route_val = dec if isinstance(dec, str) else str(dec)
                        method_val = "ANY"
                        for http_m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                            if http_m.lower() in dec_str:
                                method_val = http_m
                                break
                        api_endpoints.append({
                            "symbol_id": symbol.symbol_id,
                            "name": symbol.name,
                            "route": route_val,
                            "method": method_val,
                            "file_path": symbol_file.file_path,
                            "file_id": str(symbol.file_id),
                            "via": "self",
                        })
                        break

        return api_endpoints

    # ── public: workflows ─────────────────────────────────────────────

    async def get_affected_workflows(self, symbol_id: str) -> list[dict]:
        """Find CI/CD workflows that exercise code paths using this symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return []

        # Find test files that cover this symbol
        tests = await self.get_tests_for_symbol(symbol_id)
        if not tests:
            return []

        # Find workflow/CI files in the repository
        workflow_patterns = (
            ".github/workflows",
            ".gitlab-ci",
            "Jenkinsfile",
            ".circleci",
            ".travis.yml",
            "azure-pipelines",
            "cloudbuild",
            "bitbucket-pipelines",
        )

        repo_id = symbol.repository_id
        ci_files_stmt = select(CodeFile).where(CodeFile.repository_id == repo_id)
        ci_result = await self._db.execute(ci_files_stmt)
        all_files = ci_result.scalars().all()

        workflows: list[dict] = []
        for f in all_files:
            path = f.file_path.lower()
            is_workflow = any(p in path for p in workflow_patterns)
            if not is_workflow:
                continue
            # A workflow is affected if it runs tests that cover our symbol
            runs_test = False
            for test in tests:
                test_path = test.get("source_file_path", "")
                if test_path and test_path in path:
                    runs_test = True
                    break
            # Also: workflow references the file containing this symbol
            symbol_file = await self._resolve_file(str(symbol.file_id))
            if symbol_file and symbol_file.file_name in path:
                runs_test = True

            workflows.append({
                "file_path": f.file_path,
                "file_id": str(f.id),
                "affected_via_tests": runs_test,
                "test_count_covering": len(tests) if runs_test else 0,
            })

        return workflows

    # ── public: change scope estimation ───────────────────────────────

    async def estimate_change_scope(
        self, changed_symbols: list[str]
    ) -> ChangeScope:
        """Given a set of changed symbols, estimate total impact scope."""
        all_affected_sym_ids: set[str] = set(changed_symbols)
        all_affected_files: set[str] = set()
        all_affected_layers: set[str] = set()
        all_affected_tests: set[str] = set()
        all_affected_docs: set[str] = set()
        all_recommended: list[str] = []

        for symbol_id in changed_symbols:
            impact = await self.analyze_impact(symbol_id)

            for item in impact.dependents + impact.transitive_dependents + impact.callers:
                sid = item.get("symbol_id", "")
                if sid:
                    all_affected_sym_ids.add(sid)
                fid = item.get("file_id", "")
                if fid:
                    all_affected_files.add(fid)

            for test in impact.tests:
                test_name = test.get("test_name", "")
                if test_name:
                    all_affected_tests.add(test_name)

            for doc in impact.documentation:
                doc_path = doc.get("file_path", "")
                if doc_path:
                    all_affected_docs.add(doc_path)

            for layer in impact.affected_layers:
                all_affected_layers.add(layer)

        if len(changed_symbols) > 10:
            all_recommended.append("Consider breaking this change into smaller PRs")
        if len(all_affected_tests) > 20:
            all_recommended.append("Run full test suite before merging")
        if "infrastructure" in all_affected_layers:
            all_recommended.append("Infrastructure layer changes require extra review")
        if len(all_affected_files) > 30:
            all_recommended.append("Large blast radius — consider feature flags")

        # Compute aggregate risk
        max_risk = 0.0
        for symbol_id in changed_symbols:
            impact = await self.analyze_impact(symbol_id)
            max_risk = max(max_risk, impact.risk_score)

        # Boost risk for multi-symbol changes
        scale_factor = min(1.0 + 0.05 * len(changed_symbols), 2.0)
        aggregated_risk = min(max_risk * scale_factor, 1.0)

        estimated_effort = _estimate_effort(
            len(all_affected_files),
            len(all_affected_sym_ids),
            len(all_affected_tests),
            aggregated_risk,
        )

        return ChangeScope(
            changed_symbols=changed_symbols,
            affected_symbols=len(all_affected_sym_ids),
            affected_files=len(all_affected_files),
            affected_layers=sorted(all_affected_layers),
            risk_score=round(aggregated_risk, 4),
            risk_level=_risk_level(aggregated_risk),
            affected_tests=sorted(all_affected_tests),
            affected_docs=sorted(all_affected_docs),
            recommended_actions=all_recommended,
            estimated_effort=estimated_effort,
        )

    # ── public: breaking changes ──────────────────────────────────────

    async def detect_breaking_changes(
        self, old_symbols: list, new_symbols: list
    ) -> list[dict]:
        """Detect breaking API changes between old and new symbol definitions.

        Each entry in *old_symbols* / *new_symbols* should be a dict with
        at minimum ``name``, ``symbol_type``, and optionally ``parameters``,
        ``return_type``, ``visibility``.
        """
        old_map: dict[str, dict] = {}
        for s in old_symbols:
            name = s.get("name", "")
            if name:
                old_map[name] = s

        new_map: dict[str, dict] = {}
        for s in new_symbols:
            name = s.get("name", "")
            if name:
                new_map[name] = s

        breaking: list[dict] = []

        # Removed symbols
        for name, old_sym in old_map.items():
            if name not in new_map:
                breaking.append({
                    "type": "removed",
                    "symbol_name": name,
                    "old_definition": old_sym,
                    "new_definition": None,
                    "severity": "high",
                    "description": f"Symbol '{name}' was removed",
                })

        # Changed symbols
        for name in old_map:
            if name not in new_map:
                continue
            old_def = old_map[name]
            new_def = new_map[name]

            # Visibility change (public -> private)
            old_vis = old_def.get("visibility", "public")
            new_vis = new_def.get("visibility", "public")
            if old_vis == "public" and new_vis != "public":
                breaking.append({
                    "type": "visibility_reduced",
                    "symbol_name": name,
                    "old_definition": old_def,
                    "new_definition": new_def,
                    "severity": "medium",
                    "description": f"Symbol '{name}' visibility changed from public to {new_vis}",
                })

            # Parameter changes
            old_params = old_def.get("parameters", [])
            new_params = new_def.get("parameters", [])
            if old_params and new_params:
                old_param_names = [
                    p.get("name", p) if isinstance(p, dict) else str(p)
                    for p in old_params
                ]
                new_param_names = [
                    p.get("name", p) if isinstance(p, dict) else str(p)
                    for p in new_params
                ]
                removed_params = [
                    p for p in old_param_names if p not in new_param_names
                ]
                if removed_params:
                    breaking.append({
                        "type": "parameters_removed",
                        "symbol_name": name,
                        "old_definition": old_def,
                        "new_definition": new_def,
                        "severity": "high",
                        "description": f"Parameters removed from '{name}': {removed_params}",
                        "removed_parameters": removed_params,
                    })

                # Check for new required params without defaults
                for p in new_params:
                    if isinstance(p, dict):
                        p_name = p.get("name", "")
                        has_default = p.get("default") is not None or p.get("has_default", False)
                        if p_name and p_name not in old_param_names and not has_default:
                            breaking.append({
                                "type": "required_parameter_added",
                                "symbol_name": name,
                                "old_definition": old_def,
                                "new_definition": new_def,
                                "severity": "high",
                                "description": f"New required parameter '{p_name}' added to '{name}'",
                            })

            # Return type change
            old_ret = old_def.get("return_type")
            new_ret = new_def.get("return_type")
            if old_ret and new_ret and old_ret != new_ret:
                breaking.append({
                    "type": "return_type_changed",
                    "symbol_name": name,
                    "old_definition": old_def,
                    "new_definition": new_def,
                    "severity": "medium",
                    "description": f"Return type of '{name}' changed from {old_ret} to {new_ret}",
                })

            # Symbol type change
            old_type = old_def.get("symbol_type")
            new_type = new_def.get("symbol_type")
            if old_type and new_type and old_type != new_type:
                breaking.append({
                    "type": "type_changed",
                    "symbol_name": name,
                    "old_definition": old_def,
                    "new_definition": new_def,
                    "severity": "high",
                    "description": f"Symbol type of '{name}' changed from {old_type} to {new_type}",
                })

        return breaking

    # ── public: rename impact ─────────────────────────────────────────

    async def get_rename_impact(
        self, symbol_id: str, new_name: str
    ) -> RenameImpact:
        """Assess the impact of renaming a symbol."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return RenameImpact(
                symbol_id=symbol_id,
                old_name=symbol_id,
                new_name=new_name,
            )

        old_name = symbol.name

        # Gather all references
        ref_stmt = (
            select(CodeReference)
            .where(
                CodeReference.repository_id == symbol.repository_id,
                or_(
                    CodeReference.source_symbol_id == symbol.id,
                    CodeReference.target_symbol_id == symbol.id,
                ),
            )
        )
        ref_result = await self._db.execute(stmt=ref_stmt)
        refs = ref_result.scalars().all()

        # Gather all calls
        call_as_caller_stmt = select(CodeCall).where(
            CodeCall.caller_symbol_id == symbol.id
        )
        call_as_callee_stmt = select(CodeCall).where(
            CodeCall.callee_symbol_id == symbol.id
        )
        caller_result = await self._db.execute(call_as_caller_stmt)
        callee_result = await self._db.execute(call_as_callee_stmt)
        caller_calls = caller_result.scalars().all()
        callee_calls = callee_result.scalars().all()

        # Gather imports
        import_stmt = select(CodeImport).where(
            CodeImport.imported_symbol_id == symbol.id
        )
        import_result = await self._db.execute(import_stmt)
        imports = import_result.scalars().all()

        # Files to modify
        file_ids_to_modify: set[str] = set()
        references_to_update = 0

        for ref in refs:
            if ref.source_file_id:
                file_ids_to_modify.add(str(ref.source_file_id))
            references_to_update += 1

        for call in caller_calls:
            file_ids_to_modify.add(str(call.caller_file_id))
            references_to_update += 1

        for call in callee_calls:
            file_ids_to_modify.add(str(call.caller_file_id))
            references_to_update += 1

        for imp in imports:
            file_ids_to_modify.add(str(imp.source_file_id))
            references_to_update += 1

        # Resolve file paths
        files_to_modify = await self._resolve_file_paths(file_ids_to_modify)

        # Tests
        tests = await self.get_tests_for_symbol(symbol_id)
        affected_test_names = [t["test_name"] for t in tests]
        for t in tests:
            fid = t.get("file_id", "")
            if fid:
                file_ids_to_modify.add(fid)
                files_to_modify = sorted(
                    set(files_to_modify + await self._resolve_file_paths({fid}))
                )

        # Breaking changes: public API symbols that are imported externally
        breaking_changes: list[dict] = []
        is_public = symbol.visibility in ("public", None)
        if is_public and imports:
            for imp in imports:
                if imp.is_external:
                    breaking_changes.append({
                        "type": "external_import",
                        "imported_name": imp.imported_name,
                        "source_file_id": str(imp.source_file_id),
                        "description": f"External package imports '{old_name}' as '{imp.imported_name}'",
                    })

        # Auto-fixable if no external breaking changes
        auto_fixable = len(breaking_changes) == 0

        # Risk score
        ref_factor = min(references_to_update / 50.0, 1.0)
        file_factor = min(len(file_ids_to_modify) / 20.0, 1.0)
        breaking_factor = min(len(breaking_changes) * 0.3, 1.0)
        risk = min(
            0.15 * ref_factor + 0.35 * file_factor + 0.5 * breaking_factor,
            1.0,
        )

        return RenameImpact(
            symbol_id=symbol.symbol_id,
            old_name=old_name,
            new_name=new_name,
            files_to_modify=files_to_modify,
            references_to_update=references_to_update,
            breaking_changes=breaking_changes,
            risk_score=round(risk, 4),
            auto_fixable=auto_fixable,
            affected_tests=affected_test_names,
        )

    # ── public: move impact ───────────────────────────────────────────

    async def get_move_impact(
        self, symbol_id: str, new_file: str
    ) -> MoveImpact:
        """Assess the impact of moving a symbol to a new file."""
        symbol = await self._resolve_symbol(symbol_id)
        if symbol is None:
            return MoveImpact(
                symbol_id=symbol_id,
                old_file=symbol_id,
                new_file=new_file,
            )

        old_file_row = await self._resolve_file(str(symbol.file_id))
        old_file = old_file_row.file_path if old_file_row else ""

        # All imports referencing this symbol
        import_stmt = select(CodeImport).where(
            CodeImport.imported_symbol_id == symbol.id
        )
        import_result = await self._db.execute(import_stmt)
        imports = import_result.scalars().all()

        imports_to_update: list[dict] = []
        for imp in imports:
            source_file = await self._resolve_file(str(imp.source_file_id))
            imports_to_update.append({
                "source_file_path": source_file.file_path if source_file else "",
                "source_file_id": str(imp.source_file_id),
                "imported_name": imp.imported_name,
                "alias": imp.alias,
                "import_type": imp.import_type,
            })

        # References
        ref_stmt = select(CodeReference).where(
            or_(
                CodeReference.source_symbol_id == symbol.id,
                CodeReference.target_symbol_id == symbol.id,
            )
        )
        ref_result = await self._db.execute(ref_stmt)
        refs = ref_result.scalars().all()
        references_to_update = len(refs)

        # Calls
        call_stmt = or_(
            CodeCall.caller_symbol_id == symbol.id,
            CodeCall.callee_symbol_id == symbol.id,
        )
        call_result = await self._db.execute(select(CodeCall).where(call_stmt))
        calls = call_result.scalars().all()
        references_to_update += len(calls)

        # Breaking changes if symbol is part of public package
        breaking_changes: list[dict] = []
        is_public = symbol.visibility in ("public", None)
        if is_public:
            for imp in imports:
                if imp.is_external:
                    breaking_changes.append({
                        "type": "external_import_path_changed",
                        "imported_name": imp.imported_name,
                        "old_file": old_file,
                        "new_file": new_file,
                        "description": (
                            f"External package imports from '{old_file}' "
                            f"which will change to '{new_file}'"
                        ),
                    })

        auto_fixable = len(breaking_changes) == 0

        # Risk
        import_factor = min(len(imports_to_update) / 30.0, 1.0)
        ref_factor = min(references_to_update / 50.0, 1.0)
        breaking_factor = min(len(breaking_changes) * 0.4, 1.0)
        risk = min(
            0.25 * import_factor + 0.35 * ref_factor + 0.4 * breaking_factor,
            1.0,
        )

        return MoveImpact(
            symbol_id=symbol.symbol_id,
            old_file=old_file,
            new_file=new_file,
            imports_to_update=imports_to_update,
            references_to_update=references_to_update,
            breaking_changes=breaking_changes,
            risk_score=round(risk, 4),
            auto_fixable=auto_fixable,
        )

    # ── public: dead code detection ───────────────────────────────────

    async def find_unused_symbols(self, repo_id: str) -> list[dict]:
        """Find symbols with zero inbound references (removal candidates)."""
        symbols_stmt = select(CodeSymbol).where(
            CodeSymbol.repository_id == _uuid.UUID(repo_id),
            CodeSymbol.symbol_type.in_([
                "FUNCTION", "METHOD", "CLASS", "VARIABLE", "CONSTANT",
            ]),
        )
        result = await self._db.execute(symbols_stmt)
        symbols = result.scalars().all()

        unused: list[dict] = []
        for sym in symbols:
            # Check inbound references
            ref_stmt = select(func.count()).where(
                CodeReference.target_symbol_id == sym.id,
                CodeReference.reference_type != ReferenceType.DEFINITION.value,
            )
            ref_result = await self._db.execute(ref_stmt)
            ref_count = ref_result.scalar() or 0

            # Check inbound calls
            call_stmt = select(func.count()).where(
                CodeCall.callee_symbol_id == sym.id,
            )
            call_result = await self._db.execute(call_stmt)
            call_count = call_result.scalar() or 0

            # Check inbound imports
            import_stmt = select(func.count()).where(
                CodeImport.imported_symbol_id == sym.id,
            )
            import_result = await self._db.execute(import_stmt)
            import_count = import_result.scalar() or 0

            total_refs = ref_count + call_count + import_count
            if total_refs == 0:
                # Skip private dunder methods and __init__
                if sym.name.startswith("__") and sym.name.endswith("__"):
                    continue
                if sym.symbol_type in ("IMPORT",):
                    continue

                file_row = await self._resolve_file(str(sym.file_id))
                unused.append({
                    "symbol_id": sym.symbol_id,
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "symbol_type": sym.symbol_type,
                    "file_path": file_row.file_path if file_row else "",
                    "file_id": str(sym.file_id),
                    "visibility": sym.visibility,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                })

        return unused

    async def find_dead_imports(self, repo_id: str) -> list[dict]:
        """Find imports that are not referenced anywhere in the importing file."""
        imports_stmt = select(CodeImport).where(
            CodeImport.repository_id == _uuid.UUID(repo_id),
            CodeImport.resolved.is_(True),
        )
        result = await self._db.execute(imports_stmt)
        imports = result.scalars().all()

        dead: list[dict] = []
        for imp in imports:
            imported_name = imp.imported_name
            source_file_id = imp.source_file_id

            # Get the last segment of the import as the usage name
            usage_name = imported_name.rsplit(".", 1)[-1] if "." in imported_name else imported_name
            if imp.alias:
                usage_name = imp.alias

            # Check if the usage_name appears in any reference in the same file
            ref_stmt = select(func.count()).where(
                CodeReference.source_file_id == source_file_id,
                CodeReference.target_name.ilike(f"%{usage_name}%"),
            )
            ref_result = await self._db.execute(stmt=ref_stmt)
            ref_count = ref_result.scalar() or 0

            # Also check calls in the same file
            call_stmt = select(func.count()).where(
                CodeCall.caller_file_id == source_file_id,
                CodeCall.callee_name.ilike(f"%{usage_name}%"),
            )
            call_result = await self._db.execute(call_stmt)
            call_count = call_result.scalar() or 0

            if ref_count == 0 and call_count == 0:
                file_row = await self._resolve_file(str(source_file_id))
                dead.append({
                    "import_id": str(imp.id),
                    "imported_name": imported_name,
                    "usage_name": usage_name,
                    "file_path": file_row.file_path if file_row else "",
                    "file_id": str(source_file_id),
                    "import_type": imp.import_type,
                    "is_external": imp.is_external,
                    "is_stdlib": imp.is_stdlib,
                })

        return dead

    async def find_circular_dependencies(self, repo_id: str) -> list[dict]:
        """Find circular dependency chains at both file and symbol level."""
        # Build file-level adjacency via imports and calls
        files_stmt = select(CodeFile).where(
            CodeFile.repository_id == _uuid.UUID(repo_id)
        )
        files_result = await self._db.execute(files_stmt)
        files = files_result.scalars().all()
        file_ids = {str(f.id) for f in files}
        file_path_map = {str(f.id): f.file_path for f in files}

        sym_to_file = await self._load_symbol_to_file_map(repo_id)

        adj: dict[str, set[str]] = defaultdict(set)

        # Import edges
        import_stmt = select(CodeImport).where(
            CodeImport.repository_id == _uuid.UUID(repo_id),
            CodeImport.resolved.is_(True),
        )
        import_result = await self._db.execute(import_stmt)
        for imp in import_result.scalars().all():
            src = str(imp.source_file_id)
            if imp.imported_symbol_id:
                tgt = sym_to_file.get(str(imp.imported_symbol_id), "")
                if tgt and tgt in file_ids and src != tgt:
                    adj[src].add(tgt)

        # Call edges
        call_stmt = select(CodeCall).where(
            CodeCall.repository_id == _uuid.UUID(repo_id),
            CodeCall.resolved.is_(True),
        )
        call_result = await self._db.execute(call_stmt)
        for call in call_result.scalars().all():
            src = str(call.caller_file_id)
            if call.callee_symbol_id:
                tgt = sym_to_file.get(str(call.callee_symbol_id), "")
                if tgt and tgt in file_ids and src != tgt:
                    adj[src].add(tgt)

        # DFS cycle detection
        cycles: list[dict] = []
        WHITE, GREY, BLACK = 0, 1, 2
        color: dict[str, int] = {f: WHITE for f in file_ids}
        parent: dict[str, str | None] = {}

        for node in file_ids:
            if color.get(node, WHITE) != WHITE:
                continue
            stack: list[str] = [node]
            parent[node] = None
            color[node] = GREY

            while stack:
                u = stack[-1]
                progress = False
                for v in sorted(adj.get(u, [])):
                    if color.get(v, WHITE) == WHITE:
                        color[v] = GREY
                        parent[v] = u
                        stack.append(v)
                        progress = True
                        break
                    elif color.get(v, WHITE) == GREY:
                        cycle_paths: list[str] = []
                        cur: str | None = v
                        while cur is not None:
                            cycle_paths.append(file_path_map.get(cur, cur))
                            cur = parent.get(cur)
                        cycle_paths.reverse()
                        cycle_paths.append(file_path_map.get(v, v))

                        cycles.append({
                            "cycle": cycle_paths,
                            "length": len(cycle_paths) - 1,
                            "files": cycle_paths,
                            "severity": (
                                "high" if len(cycle_paths) > 4
                                else "medium" if len(cycle_paths) > 2
                                else "low"
                            ),
                        })
                        progress = True
                        break
                if not progress:
                    stack.pop()
                    color[u] = BLACK

        return cycles

    # ── public: change history risk ───────────────────────────────────

    async def get_change_history_impact(
        self, repo_id: str, file_path: str
    ) -> dict:
        """Analyze change frequency and risk from git history."""
        stmt = (
            select(CodeHistory)
            .where(
                CodeHistory.repository_id == _uuid.UUID(repo_id),
                CodeHistory.file_path == file_path,
            )
            .order_by(CodeHistory.commit_date.desc())
        )
        result = await self._db.execute(stmt)
        history = result.scalars().all()

        if not history:
            return {
                "file_path": file_path,
                "total_commits": 0,
                "risk_score": 0.0,
                "risk_level": "LOW",
                "churn": 0,
                "frequency": "none",
                "recent_authors": [],
                "hotspot": False,
            }

        total_commits = len(history)
        total_additions = sum(h.lines_added for h in history)
        total_deletions = sum(h.lines_deleted for h in history)
        churn = total_additions + total_deletions

        authors: dict[str, dict] = {}
        for h in history:
            email = h.author_email or "unknown"
            if email not in authors:
                authors[email] = {
                    "email": email,
                    "name": h.author_name,
                    "commits": 0,
                    "lines_changed": 0,
                }
            authors[email]["commits"] += 1
            authors[email]["lines_changed"] += h.lines_added + h.lines_deleted

        recent_authors = sorted(
            authors.values(), key=lambda a: a["commits"], reverse=True
        )

        # Calculate recency: days since last commit
        now = datetime.now(timezone.utc)
        last_commit = history[0].commit_date
        if last_commit:
            if last_commit.tzinfo is None:
                last_commit = last_commit.replace(tzinfo=timezone.utc)
            days_since = (now - last_commit).days
        else:
            days_since = 999

        # Risk factors
        freq_score = min(total_commits / 50.0, 1.0)
        churn_score = min(churn / 5000.0, 1.0)
        recency_score = max(0.0, 1.0 - days_since / 90.0)
        author_spread = min(len(authors) / 10.0, 1.0)

        risk = min(
            0.25 * freq_score
            + 0.30 * churn_score
            + 0.25 * recency_score
            + 0.20 * author_spread,
            1.0,
        )

        # Determine frequency label
        if total_commits <= 2:
            frequency = "rare"
        elif total_commits <= 10:
            frequency = "occasional"
        elif total_commits <= 30:
            frequency = "regular"
        else:
            frequency = "frequent"

        hotspot = total_commits > 20 and churn > 2000

        return {
            "file_path": file_path,
            "total_commits": total_commits,
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "churn": churn,
            "frequency": frequency,
            "risk_score": round(risk, 4),
            "risk_level": _risk_level(risk),
            "recent_authors": recent_authors[:10],
            "hotspot": hotspot,
            "days_since_last_commit": days_since,
        }

    # ── private: BFS graph traversal ──────────────────────────────────

    async def _traverse_graph(
        self,
        start_id: str,
        direction: str,
        edge_types: list[str],
        max_depth: int,
    ) -> list[dict]:
        """BFS traversal of the code graph.

        direction: ``"upstream"`` follows edges *toward* the start node
        (things that depend on it), ``"downstream"`` follows edges *away*
        from it (things it depends on).
        """
        symbol = await self._resolve_symbol(start_id)
        if symbol is None:
            return []

        visited: set[str] = {symbol.symbol_id}
        queue: deque[tuple[str, int]] = deque([(symbol.symbol_id, 0)])
        results: list[dict] = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            current_sym = await self._resolve_symbol(current_id)
            if current_sym is None:
                continue

            if depth > 0:
                file_row = await self._resolve_file(str(current_sym.file_id))
                results.append({
                    "symbol_id": current_sym.symbol_id,
                    "name": current_sym.name,
                    "qualified_name": current_sym.qualified_name,
                    "symbol_type": current_sym.symbol_type,
                    "file_id": str(current_sym.file_id),
                    "file_path": file_row.file_path if file_row else "",
                    "depth": depth,
                    "layer": _classify_layer(
                        file_row.file_path if file_row else "",
                        current_sym.name,
                    ),
                })

            if direction == "upstream":
                neighbors = await self._get_upstream_neighbors(
                    current_sym.id, edge_types
                )
            else:
                neighbors = await self._get_downstream_neighbors(
                    current_sym.id, edge_types
                )

            for neighbor_sym in neighbors:
                n_sid = neighbor_sym.symbol_id
                if n_sid not in visited:
                    visited.add(n_sid)
                    queue.append((n_sid, depth + 1))

        return results

    async def _get_upstream_neighbors(
        self, db_id, edge_types: list[str]
    ) -> list[CodeSymbol]:
        """Get symbols that reference/call/import the given symbol."""
        neighbor_ids: set[str] = set()

        if ReferenceType.IMPORT.value in edge_types:
            stmt = select(CodeImport).where(
                CodeImport.imported_symbol_id == db_id,
            )
            result = await self._db.execute(stmt)
            for imp in result.scalars().all():
                file_sym_stmt = select(CodeSymbol).where(
                    CodeSymbol.file_id == imp.source_file_id,
                    CodeSymbol.symbol_type.in_(["FUNCTION", "METHOD", "CLASS"]),
                )
                fs_result = await self._db.execute(file_sym_stmt)
                for sym in fs_result.scalars().all():
                    neighbor_ids.add(sym.symbol_id)

        if ReferenceType.CALL.value in edge_types:
            stmt = select(CodeCall).where(
                CodeCall.callee_symbol_id == db_id,
            )
            result = await self._db.execute(stmt)
            for call in result.scalars().all():
                caller = await self._resolve_symbol_db_id(call.caller_symbol_id)
                if caller:
                    neighbor_ids.add(caller.symbol_id)

        if ReferenceType.REFERENCE.value in edge_types:
            stmt = select(CodeReference).where(
                CodeReference.target_symbol_id == db_id,
                CodeReference.reference_type == ReferenceType.REFERENCE.value,
            )
            result = await self._db.execute(stmt)
            for ref in result.scalars().all():
                if ref.source_symbol_id:
                    source = await self._resolve_symbol_db_id(ref.source_symbol_id)
                    if source:
                        neighbor_ids.add(source.symbol_id)

        if ReferenceType.INHERITANCE.value in edge_types:
            stmt = select(CodeReference).where(
                CodeReference.target_symbol_id == db_id,
                CodeReference.reference_type == ReferenceType.INHERITANCE.value,
            )
            result = await self._db.execute(stmt)
            for ref in result.scalars().all():
                if ref.source_symbol_id:
                    source = await self._resolve_symbol_db_id(ref.source_symbol_id)
                    if source:
                        neighbor_ids.add(source.symbol_id)

        if ReferenceType.IMPLEMENTATION.value in edge_types:
            stmt = select(CodeReference).where(
                CodeReference.target_symbol_id == db_id,
                CodeReference.reference_type == ReferenceType.IMPLEMENTATION.value,
            )
            result = await self._db.execute(stmt)
            for ref in result.scalars().all():
                if ref.source_symbol_id:
                    source = await self._resolve_symbol_db_id(ref.source_symbol_id)
                    if source:
                        neighbor_ids.add(source.symbol_id)

        if not neighbor_ids:
            return []

        symbols: list[CodeSymbol] = []
        # Batch fetch
        all_syms_stmt = select(CodeSymbol).where(
            CodeSymbol.symbol_id.in_(neighbor_ids)
        )
        result = await self._db.execute(all_syms_stmt)
        symbols = list(result.scalars().all())
        return symbols

    async def _get_downstream_neighbors(
        self, db_id, edge_types: list[str]
    ) -> list[CodeSymbol]:
        """Get symbols that the given symbol references/calls/imports."""
        neighbor_ids: set[str] = set()

        if ReferenceType.CALL.value in edge_types:
            stmt = select(CodeCall).where(
                CodeCall.caller_symbol_id == db_id,
            )
            result = await self._db.execute(stmt)
            for call in result.scalars().all():
                callee = await self._resolve_symbol_db_id(call.callee_symbol_id)
                if callee:
                    neighbor_ids.add(callee.symbol_id)

        if ReferenceType.REFERENCE.value in edge_types:
            stmt = select(CodeReference).where(
                CodeReference.source_symbol_id == db_id,
                CodeReference.reference_type == ReferenceType.REFERENCE.value,
            )
            result = await self._db.execute(stmt)
            for ref in result.scalars().all():
                if ref.target_symbol_id:
                    target = await self._resolve_symbol_db_id(ref.target_symbol_id)
                    if target:
                        neighbor_ids.add(target.symbol_id)

        if ReferenceType.IMPORT.value in edge_types:
            stmt = select(CodeImport).where(
                CodeImport.source_file_id == db_id,
            )
            result = await self._db.execute(stmt)
            for imp in result.scalars().all():
                if imp.imported_symbol_id:
                    target = await self._resolve_symbol_db_id(imp.imported_symbol_id)
                    if target:
                        neighbor_ids.add(target.symbol_id)

        if ReferenceType.INHERITANCE.value in edge_types:
            stmt = select(CodeReference).where(
                CodeReference.source_symbol_id == db_id,
                CodeReference.reference_type == ReferenceType.INHERITANCE.value,
            )
            result = await self._db.execute(stmt)
            for ref in result.scalars().all():
                if ref.target_symbol_id:
                    target = await self._resolve_symbol_db_id(ref.target_symbol_id)
                    if target:
                        neighbor_ids.add(target.symbol_id)

        if ReferenceType.IMPLEMENTATION.value in edge_types:
            stmt = select(CodeReference).where(
                CodeReference.source_symbol_id == db_id,
                CodeReference.reference_type == ReferenceType.IMPLEMENTATION.value,
            )
            result = await self._db.execute(stmt)
            for ref in result.scalars().all():
                if ref.target_symbol_id:
                    target = await self._resolve_symbol_db_id(ref.target_symbol_id)
                    if target:
                        neighbor_ids.add(target.symbol_id)

        if not neighbor_ids:
            return []

        all_syms_stmt = select(CodeSymbol).where(
            CodeSymbol.symbol_id.in_(neighbor_ids)
        )
        result = await self._db.execute(all_syms_stmt)
        return list(result.scalars().all())

    # ── private: risk scoring ─────────────────────────────────────────

    def _calculate_risk_score(self, impact: ImpactResult) -> float:
        """Calculate risk score (0-1) based on blast radius components."""
        # Weight each factor
        w_dependents = 0.15
        w_transitive = 0.10
        w_callers = 0.15
        w_tests = 0.10
        w_files = 0.15
        w_layers = 0.10
        w_api = 0.15
        w_workflows = 0.10

        # Normalize each factor to 0-1
        n_dependents = min(len(impact.dependents) / 20.0, 1.0)
        n_transitive = min(len(impact.transitive_dependents) / 50.0, 1.0)
        n_callers = min(len(impact.callers) / 15.0, 1.0)
        n_tests = min(len(impact.tests) / 10.0, 1.0)
        n_files = min(impact.affected_files / 25.0, 1.0)
        n_layers = min(len(impact.affected_layers) / 4.0, 1.0)
        n_api = min(len(impact.api_endpoints) / 5.0, 1.0)
        n_workflows = min(len(impact.workflows) / 3.0, 1.0)

        raw = (
            w_dependents * n_dependents
            + w_transitive * n_transitive
            + w_callers * n_callers
            + w_tests * n_tests
            + w_files * n_files
            + w_layers * n_layers
            + w_api * n_api
            + w_workflows * n_workflows
        )

        return min(round(raw, 4), 1.0)

    # ── private: layer grouping ───────────────────────────────────────

    @staticmethod
    def _group_by_layer(impacts: list[dict]) -> dict[str, list[dict]]:
        """Group impacted items by architectural layer."""
        groups: dict[str, list[dict]] = defaultdict(list)
        for item in impacts:
            layer = item.get("layer", "unknown")
            groups[layer].append(item)
        return dict(groups)

    # ── private: resolution helpers ───────────────────────────────────

    async def _resolve_symbol(self, symbol_id: str) -> CodeSymbol | None:
        """Resolve a symbol by its canonical symbol_id string."""
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_symbol_db_id(self, db_id) -> CodeSymbol | None:
        """Resolve a symbol by its database UUID primary key."""
        if db_id is None:
            return None
        try:
            if isinstance(db_id, str):
                db_id = _uuid.UUID(db_id)
        except (ValueError, AttributeError):
            return None
        stmt = select(CodeSymbol).where(CodeSymbol.id == db_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_file(self, file_id: str) -> CodeFile | None:
        """Resolve a file by its database UUID string."""
        try:
            fid = _uuid.UUID(file_id)
        except (ValueError, AttributeError):
            return None
        stmt = select(CodeFile).where(CodeFile.id == fid)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_file_paths(self, file_ids: set[str]) -> list[str]:
        """Resolve a set of file ID strings to their file paths."""
        if not file_ids:
            return []
        int_ids: list[_uuid.UUID] = []
        for fid in file_ids:
            try:
                int_ids.append(_uuid.UUID(fid))
            except (ValueError, AttributeError):
                continue
        if not int_ids:
            return []

        stmt = select(CodeFile).where(CodeFile.id.in_(int_ids))
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return sorted({r.file_path for r in rows})

    async def _get_file_dependencies(self, file_id: str) -> list[dict]:
        """Collect all dependencies for a file (imports + calls out)."""
        deps: list[dict] = []

        import_stmt = select(CodeImport).where(
            CodeImport.source_file_id == file_id
        )
        import_result = await self._db.execute(import_stmt)
        for imp in import_result.scalars().all():
            target_sym = None
            if imp.imported_symbol_id:
                target_sym = await self._resolve_symbol_db_id(imp.imported_symbol_id)
            deps.append({
                "type": "import",
                "imported_name": imp.imported_name,
                "target_symbol_id": target_sym.symbol_id if target_sym else None,
                "target_name": target_sym.name if target_sym else imp.imported_name,
                "is_external": imp.is_external,
                "is_stdlib": imp.is_stdlib,
            })

        call_stmt = select(CodeCall).where(
            CodeCall.caller_file_id == file_id
        )
        call_result = await self._db.execute(call_stmt)
        for call in call_result.scalars().all():
            callee = await self._resolve_symbol_db_id(call.callee_symbol_id)
            deps.append({
                "type": "call",
                "callee_name": call.callee_name,
                "target_symbol_id": callee.symbol_id if callee else None,
                "target_name": callee.name if callee else call.callee_name,
                "resolved": call.resolved,
            })

        return deps

    async def _load_symbol_to_file_map(self, repo_id: str) -> dict[str, str]:
        """Map symbol DB id (str) -> file_id (str) for a repo."""
        stmt = select(CodeSymbol).where(
            CodeSymbol.repository_id == _uuid.UUID(repo_id)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return {str(r.id): str(r.file_id) for r in rows}


# ── effort estimation helper ──────────────────────────────────────────


def _estimate_effort(
    affected_files: int,
    affected_symbols: int,
    affected_tests: int,
    risk_score: float,
) -> str:
    """Estimate change effort from scope metrics."""
    complexity = (
        affected_files * 1.0
        + affected_symbols * 0.5
        + affected_tests * 0.3
        + risk_score * 20.0
    )
    if complexity < 5:
        return "small"
    if complexity < 20:
        return "medium"
    if complexity < 50:
        return "large"
    return "very_large"
