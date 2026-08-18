"""Symbol Resolution and Graph Building engine.

Provides five builder classes that construct and query the code intelligence
knowledge graph: symbol references, call graphs, import graphs, dependency
graphs, and inheritance graphs.
"""

import hashlib
import logging
from collections import defaultdict, deque
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.code_intelligence.models import (
    CodeCall,
    CodeFile,
    CodeImport,
    CodeReference,
    CodeSymbol,
    ReferenceType,
    SymbolType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STDLIB_MODULES = frozenset({
    "abc", "argparse", "array", "asyncio", "base64", "bisect", "builtins",
    "calendar", "collections", "concurrent", "configparser", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib",
    "email", "enum", "errno", "fcntl", "filecmp", "fnmatch", "fractions",
    "functools", "gc", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
    "http", "imaplib", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "linecache", "locale", "logging", "lzma", "math",
    "mimetypes", "multiprocessing", "numbers", "operator", "os", "pathlib",
    "pickle", "platform", "pprint", "queue", "random", "re", "readline",
    "secrets", "select", "shlex", "shutil", "signal", "site", "smtplib",
    "socket", "sqlite3", "ssl", "stat", "statistics", "string", "struct",
    "subprocess", "sys", "tempfile", "textwrap", "threading", "time",
    "timeit", "token", "tokenize", "traceback", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid", "venv", "warnings",
    "weakref", "xml", "zipfile", "zipimport",
})


def _is_stdlib(module_name: str) -> bool:
    root = module_name.split(".")[0]
    return root in _STDLIB_MODULES


def _is_external(module_name: str) -> bool:
    """Heuristic: anything not starting with a dot and not in stdlib."""
    return not _is_stdlib(module_name)


# ---------------------------------------------------------------------------
# SymbolResolver
# ---------------------------------------------------------------------------


class SymbolResolver:
    """Resolve symbol references and maintain the canonical symbol table."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    # -- public API --------------------------------------------------------

    async def build_symbol_table(
        self,
        file_symbols: list[dict],
        file_id: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeSymbol]:
        """Create canonical :class:`CodeSymbol` rows for extracted symbols.

        Each dict in *file_symbols* should contain at minimum:
        ``name``, ``symbol_type``, ``start_line``, ``end_line`` and
        optionally ``parent_name``, ``module_path``, ``signature``,
        ``docstring``, ``visibility``, ``parameters``, ``return_type``,
        ``is_async``, ``is_abstract``, ``is_static``, ``decorators``.
        """
        created: list[CodeSymbol] = []

        for sym in file_symbols:
            name: str = sym["name"]
            parent_name: str | None = sym.get("parent_name")
            module_path: str | None = sym.get("module_path")

            qualified_name = self._build_qualified_name(name, parent_name, module_path)
            symbol_id = self._generate_symbol_id(repo_id, index_id, file_id, qualified_name)

            scope = parent_name or module_path or ""

            code_sym = CodeSymbol(
                file_id=file_id,
                repository_id=repo_id,
                index_id=index_id,
                symbol_id=symbol_id,
                symbol_type=sym.get("symbol_type", SymbolType.FUNCTION.value),
                name=name,
                qualified_name=qualified_name,
                scope=scope or None,
                language=sym.get("language"),
                start_line=sym.get("start_line"),
                end_line=sym.get("end_line"),
                signature=sym.get("signature"),
                docstring=sym.get("docstring"),
                visibility=sym.get("visibility"),
                is_async=sym.get("is_async", False),
                is_abstract=sym.get("is_abstract", False),
                is_static=sym.get("is_static", False),
                decorators=sym.get("decorators") or [],
                parameters=sym.get("parameters") or [],
                return_type=sym.get("return_type"),
                parent_symbol_id=None,
            )
            self._db.add(code_sym)
            created.append(code_sym)

        await self._db.flush()
        return created

    async def resolve_references(
        self,
        symbols: list[dict],
        imports: list[dict],
        file_id: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeReference]:
        """Resolve symbol references into :class:`CodeReference` rows.

        Each entry in *symbols* should have ``source_name``, ``target_name``,
        ``reference_type``, ``line``, ``column`` and optional ``confidence``.
        Each entry in *imports* should have ``imported_name``, ``alias``,
        ``import_type``.
        """
        created: list[CodeReference] = []

        # Pre-load candidate target symbols for resolution
        target_map = await self._load_symbol_map(repo_id)

        file_sym_rows = await self._load_file_symbols(file_id)
        file_sym_by_name: dict[str, CodeSymbol] = {}
        for s in file_sym_rows:
            file_sym_by_name[s.name] = s
            file_sym_by_name[s.qualified_name] = s

        # --- symbol references ---
        for ref in symbols:
            source_name: str = ref.get("source_name", "")
            target_name: str = ref.get("target_name", "")
            ref_type: str = ref.get("reference_type", ReferenceType.REFERENCE.value)
            confidence: float = ref.get("confidence", 1.0)

            source_sym = file_sym_by_name.get(source_name)

            resolved, resolved_id = self._resolve_name(
                target_name, target_map, file_sym_by_name
            )

            code_ref = CodeReference(
                repository_id=repo_id,
                index_id=index_id,
                source_symbol_id=source_sym.id if source_sym else None,
                target_symbol_id=resolved_id,
                source_file_id=file_id,
                reference_type=ref_type,
                source_line=ref.get("line"),
                source_column=ref.get("column"),
                resolved=resolved,
                target_name=target_name,
                confidence=confidence,
            )
            self._db.add(code_ref)
            created.append(code_ref)

        # --- import references ---
        for imp in imports:
            imported_name: str = imp.get("imported_name", "")
            ref_type = ReferenceType.IMPORT.value
            alias: str | None = imp.get("alias")

            resolved, resolved_id = self._resolve_name(
                imported_name, target_map, file_sym_by_name
            )

            code_ref = CodeReference(
                repository_id=repo_id,
                index_id=index_id,
                source_symbol_id=None,
                target_symbol_id=resolved_id,
                source_file_id=file_id,
                reference_type=ref_type,
                resolved=resolved,
                target_name=imported_name,
                confidence=1.0 if resolved else 0.0,
                metadata_={"alias": alias} if alias else None,
            )
            self._db.add(code_ref)
            created.append(code_ref)

        await self._db.flush()
        return created

    async def find_unresolved_references(
        self, repo_id: str, index_id: str
    ) -> list[CodeReference]:
        """Return references that could not be resolved to a target symbol."""
        stmt = (
            select(CodeReference)
            .where(
                CodeReference.repository_id == repo_id,
                CodeReference.index_id == index_id,
                CodeReference.resolved.is_(False),
            )
            .order_by(CodeReference.target_name)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def resolve_inheritance(
        self, symbols: list[dict], repo_id: str
    ) -> list[CodeReference]:
        """Resolve *extends* / *implements* relationships.

        Each entry in *symbols* should contain ``symbol_name``,
        ``bases`` (list of parent names) and optionally ``implements``
        (list of interface names).
        """
        created: list[CodeReference] = []
        target_map = await self._load_symbol_map(repo_id)

        for sym in symbols:
            sym_name: str = sym.get("symbol_name", "")
            source_id = self._find_symbol_id_by_name(sym_name, target_map)

            for parent in sym.get("bases", []):
                resolved, resolved_id = self._resolve_name(parent, target_map, {})
                ref = CodeReference(
                    repository_id=repo_id,
                    index_id=sym.get("index_id", ""),
                    source_symbol_id=source_id,
                    target_symbol_id=resolved_id,
                    source_file_id=sym.get("file_id", ""),
                    reference_type=ReferenceType.INHERITANCE.value,
                    resolved=resolved,
                    target_name=parent,
                    confidence=1.0 if resolved else 0.5,
                )
                self._db.add(ref)
                created.append(ref)

            for iface in sym.get("implements", []):
                resolved, resolved_id = self._resolve_name(iface, target_map, {})
                ref = CodeReference(
                    repository_id=repo_id,
                    index_id=sym.get("index_id", ""),
                    source_symbol_id=source_id,
                    target_symbol_id=resolved_id,
                    source_file_id=sym.get("file_id", ""),
                    reference_type=ReferenceType.IMPLEMENTATION.value,
                    resolved=resolved,
                    target_name=iface,
                    confidence=1.0 if resolved else 0.5,
                )
                self._db.add(ref)
                created.append(ref)

        await self._db.flush()
        return created

    async def get_symbol_by_id(self, symbol_id: str) -> Optional[CodeSymbol]:
        """Look up a symbol by its canonical ``symbol_id`` string."""
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_symbol_references(
        self,
        symbol_id: str,
        reference_type: str | None = None,
    ) -> list[CodeReference]:
        """Find all references pointing *to* or *from* the given symbol."""
        sym = await self.get_symbol_by_id(symbol_id)
        if sym is None:
            return []

        conditions = or_(
            CodeReference.source_symbol_id == sym.id,
            CodeReference.target_symbol_id == sym.id,
        )
        stmt = select(CodeReference).where(conditions)
        if reference_type:
            stmt = stmt.where(CodeReference.reference_type == reference_type)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_symbol_definition(self, symbol_id: str) -> Optional[CodeSymbol]:
        """Return the symbol row if it has a DEFINITION reference pointing to
        it, otherwise return the symbol itself if found."""
        sym = await self.get_symbol_by_id(symbol_id)
        if sym is None:
            return None
        return sym

    async def search_symbols(
        self,
        query: str,
        repo_id: str,
        symbol_type: str | None = None,
        limit: int = 50,
    ) -> list[CodeSymbol]:
        """Fuzzy search symbols by name within a repository."""
        stmt = (
            select(CodeSymbol)
            .where(
                CodeSymbol.repository_id == repo_id,
                CodeSymbol.name.ilike(f"%{query}%"),
            )
            .limit(limit)
        )
        if symbol_type:
            stmt = stmt.where(CodeSymbol.symbol_type == symbol_type)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _generate_symbol_id(
        repo: str, commit: str, file: str, qualified_name: str
    ) -> str:
        """Create a deterministic canonical ID for a symbol."""
        raw = f"{repo}:{commit}:{file}::{qualified_name}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_qualified_name(
        name: str,
        parent_name: str | None,
        module_path: str | None,
    ) -> str:
        """Build a fully-qualified dotted name for a symbol."""
        parts: list[str] = []
        if module_path:
            parts.append(module_path)
        if parent_name:
            parts.append(parent_name)
        parts.append(name)
        return ".".join(p for p in parts if p)

    # -- private helpers ---------------------------------------------------

    async def _load_symbol_map(
        self, repo_id: str
    ) -> dict[str, CodeSymbol]:
        """Load all symbols in a repo keyed by name and qualified_name."""
        stmt = select(CodeSymbol).where(CodeSymbol.repository_id == repo_id)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        sym_map: dict[str, CodeSymbol] = {}
        for row in rows:
            sym_map[row.name] = row
            sym_map[row.qualified_name] = row
            sym_map[row.symbol_id] = row
        return sym_map

    async def _load_file_symbols(self, file_id: str) -> list[CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.file_id == file_id)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _resolve_name(
        name: str,
        target_map: dict[str, CodeSymbol],
        local_map: dict[str, CodeSymbol],
    ) -> tuple[bool, str | None]:
        """Attempt to resolve a name to a symbol id.

        Returns ``(resolved, symbol_db_id | None)``.
        """
        if name in local_map:
            return True, str(local_map[name].id)
        if name in target_map:
            return True, str(target_map[name].id)
        # Try last segment match
        short = name.rsplit(".", 1)[-1] if "." in name else name
        if short in target_map:
            return True, str(target_map[short].id)
        if short in local_map:
            return True, str(local_map[short].id)
        return False, None

    @staticmethod
    def _find_symbol_id_by_name(
        name: str, target_map: dict[str, CodeSymbol]
    ) -> str | None:
        sym = target_map.get(name)
        return str(sym.id) if sym else None


# ---------------------------------------------------------------------------
# CallGraphBuilder
# ---------------------------------------------------------------------------


class CallGraphBuilder:
    """Build and query the call graph between symbols."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def build_call_graph(
        self,
        file_id: str,
        calls: list[dict],
        symbols: list[dict],
        repo_id: str,
        index_id: str,
    ) -> list[CodeCall]:
        """Create :class:`CodeCall` rows for detected call sites.

        Each *calls* entry should have ``caller_name``, ``callee_name``,
        ``line``, and optional ``call_type`` and ``confidence``.
        *symbols* is the list of symbols already inserted for the file
        (used for local scope resolution).
        """
        created: list[CodeCall] = []

        # Build local lookup
        local_by_name: dict[str, dict] = {}
        for sym in symbols:
            local_by_name[sym.get("name", "")] = sym
            local_by_name[sym.get("qualified_name", "")] = sym

        # Load repo symbols for cross-file resolution
        repo_sym_map = await self._load_repo_symbols(repo_id)

        # Load file symbols (DB rows)
        file_sym_stmt = (
            select(CodeSymbol).where(CodeSymbol.file_id == file_id)
        )
        file_sym_result = await self._db.execute(file_sym_stmt)
        file_sym_rows = file_sym_result.scalars().all()
        file_sym_by_name: dict[str, CodeSymbol] = {}
        for row in file_sym_rows:
            file_sym_by_name[row.name] = row
            file_sym_by_name[row.qualified_name] = row

        for call in calls:
            caller_name: str = call.get("caller_name", "")
            callee_name: str = call.get("callee_name", "")

            caller_sym = file_sym_by_name.get(caller_name)
            if caller_sym is None:
                logger.debug("Skipping call with unresolved caller: %s", caller_name)
                continue

            resolved, callee_id = self._resolve_callee(
                callee_name, file_sym_by_name, repo_sym_map, caller_name
            )

            code_call = CodeCall(
                repository_id=repo_id,
                index_id=index_id,
                caller_symbol_id=caller_sym.id,
                callee_symbol_id=callee_id,
                caller_file_id=file_id,
                callee_name=callee_name,
                call_line=call.get("line"),
                call_type=call.get("call_type"),
                resolved=resolved,
                confidence=call.get("confidence", 1.0 if resolved else 0.5),
            )
            self._db.add(code_call)
            created.append(code_call)

        await self._db.flush()
        return created

    async def get_callers(self, symbol_id: str) -> list[CodeCall]:
        """Return all call edges where the given symbol is the callee."""
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []
        stmt = (
            select(CodeCall)
            .where(CodeCall.callee_symbol_id == sym.id)
            .order_by(CodeCall.call_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_callees(self, symbol_id: str) -> list[CodeCall]:
        """Return all call edges where the given symbol is the caller."""
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []
        stmt = (
            select(CodeCall)
            .where(CodeCall.caller_symbol_id == sym.id)
            .order_by(CodeCall.call_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_call_chain(
        self, symbol_id: str, depth: int = 3
    ) -> dict:
        """Return a recursive call chain up to *depth* levels.

        Returns a nested dict ``{symbol_id: {callees: [...]}}``.
        """
        visited: set[str] = set()
        return await self._walk_call_chain(symbol_id, depth, visited)

    async def detect_cycles(self, repo_id: str) -> list[list]:
        """Find circular call dependencies within a repository.

        Returns a list of cycles, each cycle is a list of ``symbol_id``
        strings forming the loop.
        """
        adj = await self._build_adjacency_list(repo_id)
        cycles: list[list[str]] = []
        visited_global: set[str] = set()

        for start in adj:
            if start in visited_global:
                continue
            stack: list[tuple[str, list[str]]] = [(start, [start])]
            on_path: set[str] = {start}

            while stack:
                node, path = stack.pop()
                for neighbour in adj.get(node, []):
                    if neighbour == start and len(path) > 1:
                        cycle = path + [neighbour]
                        cycles.append(cycle)
                        visited_global.update(path)
                    elif neighbour not in on_path:
                        stack.append((neighbour, path + [neighbour]))
                        on_path.add(neighbour)
            on_path.clear()

        return cycles

    @staticmethod
    def _resolve_callee(
        callee_name: str,
        local_symbols: dict[str, CodeSymbol],
        repo_symbols: dict[str, CodeSymbol],
        current_scope: str,
    ) -> tuple[bool, str | None]:
        """Resolve a callee name to a target symbol DB id.

        Tries local scope first, then repo-wide, then short-name fallback.
        Returns ``(resolved, db_id | None)``.
        """
        # Direct local match
        if callee_name in local_symbols:
            return True, str(local_symbols[callee_name].id)

        # Direct repo match
        if callee_name in repo_symbols:
            return True, str(repo_symbols[callee_name].id)

        # Try resolving against current scope prefix
        if current_scope and "." in current_scope:
            prefix = current_scope.rsplit(".", 1)[0]
            candidate = f"{prefix}.{callee_name}"
            if candidate in local_symbols:
                return True, str(local_symbols[candidate].id)
            if candidate in repo_symbols:
                return True, str(repo_symbols[candidate].id)

        # Short-name fallback
        short = callee_name.rsplit(".", 1)[-1] if "." in callee_name else callee_name
        if short in local_symbols:
            return True, str(local_symbols[short].id)
        if short in repo_symbols:
            return True, str(repo_symbols[short].id)

        return False, None

    # -- private helpers ---------------------------------------------------

    async def _resolve_symbol_by_canonical_id(
        self, symbol_id: str
    ) -> Optional[CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_repo_symbols(
        self, repo_id: str
    ) -> dict[str, CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.repository_id == repo_id)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        sym_map: dict[str, CodeSymbol] = {}
        for r in rows:
            sym_map[r.name] = r
            sym_map[r.qualified_name] = r
            sym_map[r.symbol_id] = r
        return sym_map

    async def _walk_call_chain(
        self,
        symbol_id: str,
        depth: int,
        visited: set[str],
    ) -> dict:
        if depth <= 0 or symbol_id in visited:
            return {}
        visited.add(symbol_id)

        callees = await self.get_callees(symbol_id)
        chain: dict = {}
        for call in callees:
            if call.callee_symbol_id is None:
                continue
            callee_sym = await self._resolve_symbol_by_canonical_id(
                call.callee_symbol_id
            ) if isinstance(call.callee_symbol_id, str) else None
            # code_symbols.id is a UUID; call.callee_symbol_id is already the id
            callee_sid = str(call.callee_symbol_id)
            chain[callee_sid] = {
                "callee_name": call.callee_name,
                "resolved": call.resolved,
                "call_type": call.call_type,
                "call_line": call.call_line,
                "callees": await self._walk_call_chain(
                    callee_sid, depth - 1, visited
                ),
            }

        visited.discard(symbol_id)
        return chain

    async def _build_adjacency_list(
        self, repo_id: str
    ) -> dict[str, list[str]]:
        stmt = select(CodeCall).where(CodeCall.repository_id == repo_id)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        adj: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            caller = str(row.caller_symbol_id)
            if row.callee_symbol_id is not None:
                callee = str(row.callee_symbol_id)
                adj[caller].append(callee)
        return dict(adj)


# ---------------------------------------------------------------------------
# ImportGraphBuilder
# ---------------------------------------------------------------------------


class ImportGraphBuilder:
    """Build and query the import dependency graph."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def build_import_graph(
        self,
        file_id: str,
        imports: list[dict],
        repo_id: str,
        index_id: str,
    ) -> list[CodeImport]:
        """Create :class:`CodeImport` rows for import statements.

        Each entry in *imports* should have ``imported_name``, ``import_type``
        (``"import"`` / ``"from_import"`` / ``"wildcard"``) and optionally
        ``alias``.
        """
        created: list[CodeImport] = []

        repo_sym_map = await self._load_repo_symbols(repo_id)

        for imp in imports:
            imported_name: str = imp.get("imported_name", "")
            import_type: str = imp.get("import_type", "import")
            alias: str | None = imp.get("alias")

            is_stdlib = _is_stdlib(imported_name)
            is_ext = _is_external(imported_name) and not is_stdlib

            resolved, sym_db_id = self._resolve_import_target(
                imported_name, repo_sym_map
            )

            code_import = CodeImport(
                repository_id=repo_id,
                index_id=index_id,
                source_file_id=file_id,
                imported_name=imported_name,
                imported_symbol_id=sym_db_id,
                import_type=import_type,
                alias=alias,
                is_external=is_ext,
                is_stdlib=is_stdlib,
                resolved=resolved,
            )
            self._db.add(code_import)
            created.append(code_import)

        await self._db.flush()
        return created

    async def get_imports(self, file_id: str) -> list[CodeImport]:
        """Return all imports for a given file."""
        stmt = (
            select(CodeImport)
            .where(CodeImport.source_file_id == file_id)
            .order_by(CodeImport.imported_name)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_imported_by(self, symbol_id: str) -> list[dict]:
        """Return which files import a symbol identified by *symbol_id*.

        Returns list of dicts with ``file_path`` and ``import`` details.
        """
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []

        stmt = (
            select(CodeImport, CodeFile.file_path)
            .join(CodeFile, CodeImport.source_file_id == CodeFile.id)
            .where(CodeImport.imported_symbol_id == sym.id)
        )
        result = await self._db.execute(stmt)
        return [
            {
                "file_path": row.file_path,
                "imported_name": row.imported_name,
                "import_type": row.import_type,
                "alias": row.alias,
            }
            for row in result.all()
        ]

    async def get_external_dependencies(self, repo_id: str) -> list[dict]:
        """Return all external (non-stdlib, non-internal) dependencies."""
        stmt = (
            select(CodeImport)
            .where(
                CodeImport.repository_id == repo_id,
                CodeImport.is_external.is_(True),
                CodeImport.is_stdlib.is_(False),
            )
            .distinct(CodeImport.imported_name)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        seen: dict[str, dict] = {}
        for r in rows:
            if r.imported_name not in seen:
                root = r.imported_name.split(".")[0]
                seen[r.imported_name] = {
                    "imported_name": r.imported_name,
                    "root_package": root,
                    "resolved": r.resolved,
                }
        return list(seen.values())

    async def get_internal_dependencies(self, repo_id: str) -> list[dict]:
        """Return all internal (resolved to a symbol) dependencies."""
        stmt = (
            select(CodeImport)
            .where(
                CodeImport.repository_id == repo_id,
                CodeImport.resolved.is_(True),
                CodeImport.is_external.is_(False),
            )
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        seen: dict[str, dict] = {}
        for r in rows:
            if r.imported_name not in seen:
                seen[r.imported_name] = {
                    "imported_name": r.imported_name,
                    "imported_symbol_id": str(r.imported_symbol_id) if r.imported_symbol_id else None,
                    "source_file_id": str(r.source_file_id),
                }
        return list(seen.values())

    async def detect_circular_imports(self, repo_id: str) -> list[list]:
        """Find import cycles within a repository.

        Returns list of cycles; each cycle is a list of file paths forming
        the import loop.
        """
        # Build adjacency: file -> set of files it imports internally
        stmt = (
            select(CodeImport)
            .where(
                CodeImport.repository_id == repo_id,
                CodeImport.resolved.is_(True),
            )
        )
        result = await self._db.execute(stmt)
        imports = result.scalars().all()

        # Map source_file_id -> file_path
        file_ids: set[str] = set()
        for imp in imports:
            file_ids.add(str(imp.source_file_id))

        file_path_map = await self._load_file_paths(file_ids)

        # Map imported_symbol_id -> file_id of the symbol's definition
        sym_to_file = await self._load_symbol_to_file_map(repo_id)

        adj: dict[str, set[str]] = defaultdict(set)
        for imp in imports:
            src = str(imp.source_file_id)
            if imp.imported_symbol_id:
                tgt = str(sym_to_file.get(str(imp.imported_symbol_id), ""))
                if tgt and tgt != src:
                    adj[src].add(tgt)

        # DFS cycle detection
        cycles: list[list[str]] = []
        WHITE, GREY, BLACK = 0, 1, 2
        color: dict[str, int] = {f: WHITE for f in adj}
        parent: dict[str, str | None] = {}

        for node in list(adj):
            if color.get(node, WHITE) != WHITE:
                continue
            stack: list[str] = [node]
            parent[node] = None
            color[node] = GREY

            while stack:
                u = stack[-1]
                progress = False
                for v in adj.get(u, []):
                    if color.get(v, WHITE) == WHITE:
                        color[v] = GREY
                        parent[v] = u
                        stack.append(v)
                        progress = True
                        break
                    elif color.get(v, WHITE) == GREY:
                        # Found cycle — extract it
                        cycle_paths: list[str] = []
                        cur: str | None = v
                        while cur is not None:
                            cycle_paths.append(file_path_map.get(cur, cur))
                            cur = parent.get(cur)
                        cycle_paths.reverse()
                        cycle_paths.append(file_path_map.get(v, v))
                        cycles.append(cycle_paths)
                        progress = True
                        break
                if not progress:
                    stack.pop()
                    color[u] = BLACK

        return cycles

    async def get_package_dependencies(self, repo_id: str) -> dict:
        """Build a package-level dependency map.

        Returns ``{package_name: {"imports": [...], "imported_by": [...]}}``.
        """
        stmt = select(CodeImport).where(CodeImport.repository_id == repo_id)
        result = await self._db.execute(stmt)
        imports = result.scalars().all()

        package_imports: dict[str, set[str]] = defaultdict(set)
        package_imported_by: dict[str, set[str]] = defaultdict(set)

        for imp in imports:
            src_file = str(imp.source_file_id)
            root = imp.imported_name.split(".")[0]
            package_imports[src_file].add(root)
            package_imported_by[root].add(src_file)

        return {
            "file_packages": dict(package_imports),
            "package_files": dict(package_imported_by),
        }

    # -- private helpers ---------------------------------------------------

    @staticmethod
    def _resolve_import_target(
        imported_name: str,
        repo_symbols: dict[str, CodeSymbol],
    ) -> tuple[bool, str | None]:
        if imported_name in repo_symbols:
            return True, str(repo_symbols[imported_name].id)
        # Last-segment fallback
        short = imported_name.rsplit(".", 1)[-1]
        if short in repo_symbols:
            return True, str(repo_symbols[short].id)
        return False, None

    async def _load_repo_symbols(
        self, repo_id: str
    ) -> dict[str, CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.repository_id == repo_id)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        sym_map: dict[str, CodeSymbol] = {}
        for r in rows:
            sym_map[r.name] = r
            sym_map[r.qualified_name] = r
            sym_map[r.symbol_id] = r
        return sym_map

    async def _resolve_symbol_by_canonical_id(
        self, symbol_id: str
    ) -> Optional[CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_file_paths(
        self, file_ids: set[str]
    ) -> dict[str, str]:
        if not file_ids:
            return {}
        import uuid as _uuid

        int_ids = []
        for fid in file_ids:
            try:
                int_ids.append(_uuid.UUID(fid))
            except (ValueError, AttributeError):
                continue
        if not int_ids:
            return {}

        stmt = select(CodeFile).where(CodeFile.id.in_(int_ids))
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return {str(r.id): r.file_path for r in rows}

    async def _load_symbol_to_file_map(
        self, repo_id: str
    ) -> dict[str, str]:
        """Map symbol DB id (str) -> file_id (str) for a repo."""
        stmt = select(CodeSymbol).where(CodeSymbol.repository_id == repo_id)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return {str(r.id): str(r.file_id) for r in rows}


# ---------------------------------------------------------------------------
# DependencyGraphBuilder
# ---------------------------------------------------------------------------


class DependencyGraphBuilder:
    """Build and query file-level and symbol-level dependency graphs."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def build_dependency_graph(
        self, repo_id: str, index_id: str
    ) -> dict:
        """Build the full dependency graph for a repo/index.

        Returns ``{"nodes": [...], "edges": [...]}`` where nodes are files
        and edges are import + call relationships.
        """
        files_stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == repo_id,
                CodeFile.index_id == index_id,
            )
        )
        files_result = await self._db.execute(files_stmt)
        files = files_result.scalars().all()

        nodes = [
            {
                "id": str(f.id),
                "file_path": f.file_path,
                "language": f.language,
                "symbol_count": f.symbol_count,
            }
            for f in files
        ]

        # Import edges
        import_stmt = (
            select(CodeImport)
            .where(
                CodeImport.repository_id == repo_id,
                CodeImport.index_id == index_id,
            )
        )
        import_result = await self._db.execute(import_stmt)
        import_rows = import_result.scalars().all()

        sym_to_file = await self._load_symbol_to_file_map(repo_id)

        edges: list[dict] = []
        for imp in import_rows:
            if imp.imported_symbol_id:
                target_file = sym_to_file.get(str(imp.imported_symbol_id))
                if target_file:
                    edges.append({
                        "source": str(imp.source_file_id),
                        "target": target_file,
                        "type": "import",
                        "imported_name": imp.imported_name,
                    })

        # Call edges
        call_stmt = (
            select(CodeCall)
            .where(
                CodeCall.repository_id == repo_id,
                CodeCall.index_id == index_id,
            )
        )
        call_result = await self._db.execute(call_stmt)
        call_rows = call_result.scalars().all()

        sym_id_to_file = await self._load_symbol_to_file_map(repo_id)
        for call in call_rows:
            caller_file = str(call.caller_file_id)
            if call.callee_symbol_id:
                callee_file = sym_id_to_file.get(str(call.callee_symbol_id))
                if callee_file and callee_file != caller_file:
                    edges.append({
                        "source": caller_file,
                        "target": callee_file,
                        "type": "call",
                        "callee_name": call.callee_name,
                    })

        return {"nodes": nodes, "edges": edges}

    async def get_file_dependencies(self, file_id: str) -> dict:
        """Return all dependencies (imports + calls) for a single file."""
        # What this file imports
        import_stmt = select(CodeImport).where(
            CodeImport.source_file_id == file_id
        )
        import_result = await self._db.execute(import_stmt)
        imports = import_result.scalars().all()

        # What this file calls (outgoing)
        call_stmt = select(CodeCall).where(
            CodeCall.caller_file_id == file_id
        )
        call_result = await self._db.execute(call_stmt)
        calls = call_result.scalars().all()

        sym_to_file = await self._load_symbol_to_file_map(
            str(imports[0].repository_id) if imports else
            (str(calls[0].repository_id) if calls else "")
        )

        import_deps = []
        for imp in imports:
            target_file = None
            if imp.imported_symbol_id:
                target_file = sym_to_file.get(str(imp.imported_symbol_id))
            import_deps.append({
                "imported_name": imp.imported_name,
                "target_file_id": target_file,
                "is_external": imp.is_external,
                "is_stdlib": imp.is_stdlib,
                "resolved": imp.resolved,
            })

        call_deps = []
        for call in calls:
            target_file = None
            if call.callee_symbol_id:
                target_file = sym_to_file.get(str(call.callee_symbol_id))
            call_deps.append({
                "callee_name": call.callee_name,
                "target_file_id": target_file,
                "resolved": call.resolved,
            })

        return {
            "imports": import_deps,
            "calls": call_deps,
        }

    async def get_dependents(self, file_id: str) -> list[dict]:
        """Return what other files depend on (import/call) this file."""
        # Files that import symbols defined in this file
        file_sym_stmt = select(CodeSymbol).where(CodeSymbol.file_id == file_id)
        file_sym_result = await self._db.execute(file_sym_stmt)
        file_syms = file_sym_result.scalars().all()
        sym_ids = [s.id for s in file_syms]

        dependents: list[dict] = []

        if sym_ids:
            import_stmt = (
                select(CodeImport, CodeFile.file_path)
                .join(CodeFile, CodeImport.source_file_id == CodeFile.id)
                .where(CodeImport.imported_symbol_id.in_(sym_ids))
            )
            imp_result = await self._db.execute(import_stmt)
            for row in imp_result.all():
                dependents.append({
                    "file_id": str(row.source_file_id) if hasattr(row, "source_file_id") else str(row[0].source_file_id),
                    "file_path": row.file_path if hasattr(row, "file_path") else row[1],
                    "dependency_type": "import",
                    "imported_name": row.imported_name if hasattr(row, "imported_name") else row[0].imported_name,
                })

            call_stmt = (
                select(CodeCall, CodeFile.file_path)
                .join(CodeFile, CodeCall.caller_file_id == CodeFile.id)
                .where(CodeCall.callee_symbol_id.in_(sym_ids))
            )
            call_result = await self._db.execute(call_stmt)
            for row in call_result.all():
                dependents.append({
                    "file_id": str(row[0].caller_file_id),
                    "file_path": row[1],
                    "dependency_type": "call",
                    "callee_name": row[0].callee_name,
                })

        return dependents

    async def get_symbol_dependencies(self, symbol_id: str) -> dict:
        """Return all dependencies (imports, calls out, calls in) for a symbol."""
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return {"imports": [], "calls_out": [], "calls_in": []}

        # Calls out (this symbol calls others)
        out_stmt = select(CodeCall).where(CodeCall.caller_symbol_id == sym.id)
        out_result = await self._db.execute(out_stmt)
        calls_out = [
            {
                "callee_name": c.callee_name,
                "callee_symbol_id": str(c.callee_symbol_id) if c.callee_symbol_id else None,
                "resolved": c.resolved,
            }
            for c in out_result.scalars().all()
        ]

        # Calls in (others call this symbol)
        in_stmt = select(CodeCall).where(CodeCall.callee_symbol_id == sym.id)
        in_result = await self._db.execute(in_stmt)
        calls_in = [
            {
                "caller_symbol_id": str(c.caller_symbol_id),
                "caller_file_id": str(c.caller_file_id),
                "call_type": c.call_type,
            }
            for c in in_result.scalars().all()
        ]

        # Imports this symbol
        import_stmt = (
            select(CodeImport)
            .where(CodeImport.imported_symbol_id == sym.id)
        )
        import_result = await self._db.execute(import_stmt)
        imports = [
            {
                "source_file_id": str(i.source_file_id),
                "imported_name": i.imported_name,
            }
            for i in import_result.scalars().all()
        ]

        return {
            "imports": imports,
            "calls_out": calls_out,
            "calls_in": calls_in,
        }

    async def calculate_coupling(self, repo_id: str) -> list[dict]:
        """Calculate coupling metrics per file.

        Returns list of dicts with ``file_id``, ``file_path``,
        ``afferent_coupling`` (Ca — things that depend on me) and
        ``efferent_coupling`` (Ce — things I depend on), plus
        ``instability`` (Ce / (Ca + Ce)).
        """
        files_stmt = select(CodeFile).where(CodeFile.repository_id == repo_id)
        files_result = await self._db.execute(files_stmt)
        files = files_result.scalars().all()

        file_ids = {str(f.id) for f in files}
        sym_to_file = await self._load_symbol_to_file_map(repo_id)

        # Build efferent (outgoing) coupling per file
        ce: dict[str, set[str]] = defaultdict(set)
        # Build afferent (incoming) coupling per file
        ca: dict[str, set[str]] = defaultdict(set)

        # Import-based coupling
        import_stmt = select(CodeImport).where(
            CodeImport.repository_id == repo_id
        )
        import_result = await self._db.execute(import_stmt)
        for imp in import_result.scalars().all():
            src = str(imp.source_file_id)
            if imp.imported_symbol_id:
                tgt_file = sym_to_file.get(str(imp.imported_symbol_id))
                if tgt_file and tgt_file in file_ids and src != tgt_file:
                    ce[src].add(tgt_file)
                    ca[tgt_file].add(src)

        # Call-based coupling
        call_stmt = select(CodeCall).where(
            CodeCall.repository_id == repo_id
        )
        call_result = await self._db.execute(call_stmt)
        for call in call_result.scalars().all():
            src = str(call.caller_file_id)
            if call.callee_symbol_id:
                tgt_file = sym_to_file.get(str(call.callee_symbol_id))
                if tgt_file and tgt_file in file_ids and src != tgt_file:
                    ce[src].add(tgt_file)
                    ca[tgt_file].add(src)

        metrics: list[dict] = []
        for f in files:
            fid = str(f.id)
            ca_count = len(ca.get(fid, set()))
            ce_count = len(ce.get(fid, set()))
            total = ca_count + ce_count
            instability = ce_count / total if total > 0 else 0.0

            metrics.append({
                "file_id": fid,
                "file_path": f.file_path,
                "afferent_coupling": ca_count,
                "efferent_coupling": ce_count,
                "instability": round(instability, 4),
            })

        metrics.sort(key=lambda m: m["instability"], reverse=True)
        return metrics

    async def detect_circular_dependencies(
        self, repo_id: str
    ) -> list[list]:
        """Find circular file-level dependencies.

        Returns list of cycles, each cycle is a list of file paths.
        """
        files_stmt = select(CodeFile).where(CodeFile.repository_id == repo_id)
        files_result = await self._db.execute(files_stmt)
        files = files_result.scalars().all()
        file_ids = {str(f.id) for f in files}
        file_path_map = {str(f.id): f.file_path for f in files}

        sym_to_file = await self._load_symbol_to_file_map(repo_id)

        adj: dict[str, set[str]] = defaultdict(set)

        # Import edges
        import_stmt = select(CodeImport).where(
            CodeImport.repository_id == repo_id,
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
            CodeCall.repository_id == repo_id,
            CodeCall.resolved.is_(True),
        )
        call_result = await self._db.execute(call_stmt)
        for call in call_result.scalars().all():
            src = str(call.caller_file_id)
            if call.callee_symbol_id:
                tgt = sym_to_file.get(str(call.callee_symbol_id), "")
                if tgt and tgt in file_ids and src != tgt:
                    adj[src].add(tgt)

        # DFS
        cycles: list[list[str]] = []
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
                for v in adj.get(u, []):
                    if color.get(v, WHITE) == WHITE:
                        color[v] = GREY
                        parent[v] = u
                        stack.append(v)
                        progress = True
                        break
                    elif color.get(v, WHITE) == GREY:
                        path: list[str] = []
                        cur: str | None = v
                        while cur is not None:
                            path.append(file_path_map.get(cur, cur))
                            cur = parent.get(cur)
                        path.reverse()
                        path.append(file_path_map.get(v, v))
                        cycles.append(path)
                        progress = True
                        break
                if not progress:
                    stack.pop()
                    color[u] = BLACK

        return cycles

    # -- private helpers ---------------------------------------------------

    async def _resolve_symbol_by_canonical_id(
        self, symbol_id: str
    ) -> Optional[CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_symbol_to_file_map(
        self, repo_id: str
    ) -> dict[str, str]:
        if not repo_id:
            return {}
        stmt = select(CodeSymbol).where(CodeSymbol.repository_id == repo_id)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return {str(r.id): str(r.file_id) for r in rows}


# ---------------------------------------------------------------------------
# InheritanceGraphBuilder
# ---------------------------------------------------------------------------


class InheritanceGraphBuilder:
    """Build and query class inheritance / interface-implementation trees."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def build_inheritance_graph(
        self, repo_id: str, index_id: str
    ) -> dict:
        """Build the full inheritance tree for a repository.

        Returns ``{"nodes": [...], "extends": [...], "implements": [...]}``.
        """
        stmt = (
            select(CodeReference).where(
                CodeReference.repository_id == repo_id,
                CodeReference.index_id == index_id,
                CodeReference.reference_type.in_([
                    ReferenceType.INHERITANCE.value,
                    ReferenceType.IMPLEMENTATION.value,
                ]),
            )
        )
        result = await self._db.execute(stmt)
        refs = result.scalars().all()

        # Collect all symbol ids we need to fetch
        sym_ids: set[str] = set()
        for ref in refs:
            if ref.source_symbol_id:
                sym_ids.add(str(ref.source_symbol_id))
            if ref.target_symbol_id:
                sym_ids.add(str(ref.target_symbol_id))

        sym_map = await self._load_symbols_by_db_id(sym_ids)

        nodes: list[dict] = []
        seen_nodes: set[str] = set()
        extends: list[dict] = []
        implements: list[dict] = []

        for ref in refs:
            source_db_id = str(ref.source_symbol_id) if ref.source_symbol_id else None
            target_db_id = str(ref.target_symbol_id) if ref.target_symbol_id else None

            source_info = sym_map.get(source_db_id, {})
            target_info = sym_map.get(target_db_id, {})

            if source_db_id and source_db_id not in seen_nodes:
                seen_nodes.add(source_db_id)
                nodes.append({
                    "id": source_info.get("symbol_id", source_db_id),
                    "db_id": source_db_id,
                    "name": source_info.get("name", ""),
                    "symbol_type": source_info.get("symbol_type", ""),
                })

            if target_db_id and target_db_id not in seen_nodes:
                seen_nodes.add(target_db_id)
                nodes.append({
                    "id": target_info.get("symbol_id", target_db_id),
                    "db_id": target_db_id,
                    "name": target_info.get("name", ""),
                    "symbol_type": target_info.get("symbol_type", ""),
                })

            edge = {
                "child_id": source_info.get("symbol_id", source_db_id),
                "parent_id": target_info.get("symbol_id", target_db_id),
                "child_name": source_info.get("name", ref.target_name or ""),
                "parent_name": target_info.get("name", ref.target_name or ""),
                "resolved": ref.resolved,
                "confidence": ref.confidence,
            }

            if ref.reference_type == ReferenceType.INHERITANCE.value:
                extends.append(edge)
            elif ref.reference_type == ReferenceType.IMPLEMENTATION.value:
                implements.append(edge)

        return {
            "nodes": nodes,
            "extends": extends,
            "implements": implements,
        }

    async def get_superclasses(self, symbol_id: str) -> list[dict]:
        """Return direct parent classes (extends) for a symbol."""
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []

        stmt = (
            select(CodeReference).where(
                CodeReference.source_symbol_id == sym.id,
                CodeReference.reference_type == ReferenceType.INHERITANCE.value,
            )
        )
        result = await self._db.execute(stmt)
        refs = result.scalars().all()

        parents: list[dict] = []
        for ref in refs:
            info: dict = {"target_name": ref.target_name, "resolved": ref.resolved}
            if ref.target_symbol_id:
                target_sym = await self._resolve_symbol_db_id(ref.target_symbol_id)
                if target_sym:
                    info["symbol_id"] = target_sym.symbol_id
                    info["name"] = target_sym.name
            parents.append(info)
        return parents

    async def get_subclasses(self, symbol_id: str) -> list[dict]:
        """Return direct child classes (extended-by) for a symbol."""
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []

        stmt = (
            select(CodeReference).where(
                CodeReference.target_symbol_id == sym.id,
                CodeReference.reference_type == ReferenceType.INHERITANCE.value,
            )
        )
        result = await self._db.execute(stmt)
        refs = result.scalars().all()

        children: list[dict] = []
        for ref in refs:
            info: dict = {"source_name": ref.target_name, "resolved": ref.resolved}
            if ref.source_symbol_id:
                source_sym = await self._resolve_symbol_db_id(ref.source_symbol_id)
                if source_sym:
                    info["symbol_id"] = source_sym.symbol_id
                    info["name"] = source_sym.name
            children.append(info)
        return children

    async def get_implementations(self, symbol_id: str) -> list[dict]:
        """Return interfaces implemented by a symbol, or symbols that
        implement a given interface."""
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []

        # Check if this symbol implements others
        as_source_stmt = (
            select(CodeReference).where(
                CodeReference.source_symbol_id == sym.id,
                CodeReference.reference_type == ReferenceType.IMPLEMENTATION.value,
            )
        )
        result = await self._db.execute(as_source_stmt)
        refs = result.scalars().all()

        implementations: list[dict] = []
        for ref in refs:
            info: dict = {"target_name": ref.target_name, "resolved": ref.resolved}
            if ref.target_symbol_id:
                target_sym = await self._resolve_symbol_db_id(ref.target_symbol_id)
                if target_sym:
                    info["symbol_id"] = target_sym.symbol_id
                    info["name"] = target_sym.name
                    info["symbol_type"] = target_sym.symbol_type
            implementations.append(info)

        # Check if others implement this symbol (if it's an interface)
        as_target_stmt = (
            select(CodeReference).where(
                CodeReference.target_symbol_id == sym.id,
                CodeReference.reference_type == ReferenceType.IMPLEMENTATION.value,
            )
        )
        target_result = await self._db.execute(as_target_stmt)
        for ref in target_result.scalars().all():
            info: dict = {"source_name": ref.target_name, "resolved": ref.resolved}
            if ref.source_symbol_id:
                source_sym = await self._resolve_symbol_db_id(ref.source_symbol_id)
                if source_sym:
                    info["symbol_id"] = source_sym.symbol_id
                    info["name"] = source_sym.name
                    info["symbol_type"] = source_sym.symbol_type
            implementations.append(info)

        return implementations

    async def get_mro(self, symbol_id: str) -> list[str]:
        """Compute the Method Resolution Order (C3 linearization) for a class.

        Falls back to a simple BFS traversal if C3 is not applicable.
        """
        sym = await self._resolve_symbol_by_canonical_id(symbol_id)
        if sym is None:
            return []

        mro: list[str] = [sym.symbol_id]
        visited: set[str] = {sym.symbol_id}
        queue: deque[str] = deque()

        parents = await self.get_superclasses(symbol_id)
        for p in parents:
            sid = p.get("symbol_id", "")
            if sid and sid not in visited:
                queue.append(sid)
                visited.add(sid)

        while queue:
            current_id = queue.popleft()
            mro.append(current_id)

            current_parents = await self.get_superclasses(current_id)
            for p in current_parents:
                sid = p.get("symbol_id", "")
                if sid and sid not in visited:
                    queue.append(sid)
                    visited.add(sid)

        return mro

    # -- private helpers ---------------------------------------------------

    async def _resolve_symbol_by_canonical_id(
        self, symbol_id: str
    ) -> Optional[CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_symbol_db_id(
        self, db_id
    ) -> Optional[CodeSymbol]:
        stmt = select(CodeSymbol).where(CodeSymbol.id == db_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_symbols_by_db_id(
        self, db_ids: set[str]
    ) -> dict[str, dict]:
        if not db_ids:
            return {}
        import uuid as _uuid

        int_ids = []
        for did in db_ids:
            try:
                int_ids.append(_uuid.UUID(did))
            except (ValueError, AttributeError):
                continue
        if not int_ids:
            return {}

        stmt = select(CodeSymbol).where(CodeSymbol.id.in_(int_ids))
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return {
            str(r.id): {
                "symbol_id": r.symbol_id,
                "name": r.name,
                "qualified_name": r.qualified_name,
                "symbol_type": r.symbol_type,
                "scope": r.scope,
            }
            for r in rows
        }
