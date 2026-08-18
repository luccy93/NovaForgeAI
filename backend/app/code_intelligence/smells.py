"""Code Smell Detection Engine — query-first, evidence-based."""

import hashlib
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeCall,
    CodeFile,
    CodeImport,
    CodeMetrics,
    CodeReference,
    CodeSmell,
    CodeSymbol,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "long_function_threshold": 50,
    "god_class_threshold": 20,
    "deep_nesting_threshold": 5,
    "large_param_threshold": 7,
    "high_coupling_threshold": 15,
    "large_file_threshold": 500,
    "duplicate_similarity_threshold": 0.85,
}


class SmellDetector:
    """Detect code smells by querying existing data — never re-parses source."""

    def __init__(self, db_session: AsyncSession, config: dict | None = None):
        self.db = db_session
        self.config = {**DEFAULT_CONFIG, **(config or {})}

    # ── orchestration ────────────────────────────────────────────────

    async def detect_all(
        self, repo_id: str, index_id: str
    ) -> list[CodeSmell]:
        all_smells: list[CodeSmell] = []
        detectors = [
            self.detect_long_functions,
            self.detect_god_classes,
            self.detect_deep_nesting,
            self.detect_large_parameter_lists,
            self.detect_unused_imports,
            self.detect_dead_code,
            self.detect_circular_dependencies,
            self.detect_high_coupling,
            self.detect_low_cohesion,
            self.detect_duplicate_patterns,
            self.detect_long_files,
        ]

        for detector in detectors:
            try:
                smells = await detector(repo_id)
                all_smells.extend(smells)
            except Exception:
                logger.exception("Smell detector %s failed", detector.__name__)

        self.db.add_all(all_smells)
        await self.db.flush()
        return all_smells

    # ── long functions ───────────────────────────────────────────────

    async def detect_long_functions(
        self, repo_id: str, threshold: int | None = None
    ) -> list[CodeSmell]:
        threshold = threshold or self.config["long_function_threshold"]
        stmt = (
            select(CodeSymbol, CodeMetrics, CodeFile)
            .join(CodeMetrics, and_(
                CodeMetrics.symbol_id == CodeSymbol.id,
                CodeMetrics.repository_id == UUID(repo_id),
            ))
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type.in_(["FUNCTION", "METHOD"]),
                CodeMetrics.function_length > threshold,
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for symbol, metrics, file_ in result.all():
            length = metrics.function_length or 0
            ratio = min(length / threshold, 3.0)
            confidence = round(min(0.5 + 0.17 * (ratio - 1), 0.99), 2)
            severity = "low"
            if length > threshold * 2:
                severity = "high"
            elif length > threshold * 1.5:
                severity = "medium"

            evidence = self._get_evidence(
                file_.file_path, symbol.start_line, symbol.end_line, 3
            )
            smells.append(self._create_smell(
                smell_type="long_function",
                severity=severity,
                message=f"Function '{symbol.name}' is {length} lines (threshold: {threshold})",
                evidence=evidence,
                file_path=file_.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(symbol.file_id),
                symbol_id=str(symbol.id),
            ))
        return smells

    # ── god classes ──────────────────────────────────────────────────

    async def detect_god_classes(
        self, repo_id: str, threshold: int | None = None
    ) -> list[CodeSmell]:
        threshold = threshold or self.config["god_class_threshold"]
        stmt = (
            select(
                CodeSymbol.id,
                CodeSymbol.name,
                CodeSymbol.file_id,
                CodeSymbol.start_line,
                CodeSymbol.end_line,
                CodeFile.file_path,
                func.count(CodeSymbol.id).over(
                    partition_by=CodeSymbol.parent_symbol_id,
                ).label("method_count"),
            )
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type == "CLASS",
            )
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        seen_classes: dict[str, tuple] = {}
        for row in rows:
            class_id = str(row[0])
            if class_id in seen_classes:
                continue
            seen_classes[class_id] = row

        smells = []
        for class_id, row in seen_classes.items():
            class_name = row[1]
            file_id = row[2]
            start_line = row[4]
            end_line = row[5]
            file_path = row[6]

            count_stmt = select(func.count()).where(
                CodeSymbol.parent_symbol_id == class_name,
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type == "METHOD",
            )
            count_result = await self.db.execute(count_stmt)
            method_count = count_result.scalar() or 0

            if method_count <= threshold:
                continue

            ratio = method_count / threshold
            confidence = round(min(0.5 + 0.12 * (ratio - 1), 0.95), 2)
            severity = "low"
            if method_count > threshold * 2:
                severity = "high"
            elif method_count > threshold * 1.5:
                severity = "medium"

            evidence = self._get_evidence(file_path, start_line, end_line, 5)
            smells.append(self._create_smell(
                smell_type="god_class",
                severity=severity,
                message=f"Class '{class_name}' has {method_count} methods (threshold: {threshold})",
                evidence=evidence,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(file_id),
                symbol_id=class_id,
            ))
        return smells

    # ── deep nesting ─────────────────────────────────────────────────

    async def detect_deep_nesting(
        self, repo_id: str, threshold: int | None = None
    ) -> list[CodeSmell]:
        threshold = threshold or self.config["deep_nesting_threshold"]
        stmt = (
            select(CodeMetrics, CodeSymbol, CodeFile)
            .join(CodeSymbol, CodeMetrics.symbol_id == CodeSymbol.id, isouter=True)
            .join(CodeFile, CodeMetrics.file_id == CodeFile.id)
            .where(
                CodeMetrics.repository_id == UUID(repo_id),
                CodeMetrics.nesting_depth > threshold,
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for metrics, symbol, file_ in result.all():
            depth = metrics.nesting_depth or 0
            ratio = depth / threshold
            confidence = round(min(0.6 + 0.1 * (ratio - 1), 0.98), 2)
            severity = "low"
            if depth > threshold * 2:
                severity = "high"
            elif depth > threshold * 1.5:
                severity = "medium"

            name = symbol.name if symbol else file_.file_name
            evidence = self._get_evidence(
                file_.file_path, symbol.start_line if symbol else None,
                symbol.end_line if symbol else None, 3,
            ) if symbol else ""

            smells.append(self._create_smell(
                smell_type="deep_nesting",
                severity=severity,
                message=f"'{name}' has nesting depth {depth} (threshold: {threshold})",
                evidence=evidence,
                file_path=file_.file_path,
                start_line=symbol.start_line if symbol else None,
                end_line=symbol.end_line if symbol else None,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(metrics.file_id),
                symbol_id=str(metrics.symbol_id) if metrics.symbol_id else None,
            ))
        return smells

    # ── large parameter lists ────────────────────────────────────────

    async def detect_large_parameter_lists(
        self, repo_id: str, threshold: int | None = None
    ) -> list[CodeSmell]:
        threshold = threshold or self.config["large_param_threshold"]
        stmt = (
            select(CodeSymbol, CodeFile)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type.in_(["FUNCTION", "METHOD"]),
                CodeSymbol.parameters.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for symbol, file_ in result.all():
            params = symbol.parameters or []
            if not isinstance(params, list):
                continue
            param_count = len(params)
            if param_count <= threshold:
                continue

            ratio = param_count / threshold
            confidence = round(min(0.55 + 0.15 * (ratio - 1), 0.97), 2)
            severity = "low"
            if param_count > threshold * 2:
                severity = "high"
            elif param_count > threshold * 1.5:
                severity = "medium"

            evidence = self._get_evidence(
                file_.file_path, symbol.start_line, symbol.end_line, 2,
            )
            smells.append(self._create_smell(
                smell_type="large_parameter_list",
                severity=severity,
                message=f"Function '{symbol.name}' has {param_count} parameters (threshold: {threshold})",
                evidence=evidence,
                file_path=file_.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(symbol.file_id),
                symbol_id=str(symbol.id),
            ))
        return smells

    # ── unused imports ───────────────────────────────────────────────

    async def detect_unused_imports(
        self, repo_id: str
    ) -> list[CodeSmell]:
        stmt = (
            select(CodeImport, CodeFile)
            .join(CodeFile, CodeImport.source_file_id == CodeFile.id)
            .where(
                CodeImport.repository_id == UUID(repo_id),
                CodeImport.is_external == False,
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for imp, file_ in result.all():
            ref_stmt = select(func.count()).where(
                CodeReference.repository_id == UUID(repo_id),
                CodeReference.source_file_id == imp.source_file_id,
                CodeReference.target_name == imp.imported_name,
            )
            ref_result = await self.db.execute(ref_stmt)
            ref_count = ref_result.scalar() or 0

            if ref_count > 0:
                continue

            sym_name = imp.alias or imp.imported_name.split(".")[-1]
            used_name_stmt = select(func.count()).where(
                CodeReference.repository_id == UUID(repo_id),
                CodeReference.source_file_id == imp.source_file_id,
                CodeReference.target_name.contains(sym_name),
            )
            used_result = await self.db.execute(used_name_stmt)
            used_count = used_result.scalar() or 0

            if used_count > 0:
                continue

            confidence = 0.85 if imp.resolved else 0.6
            severity = "low"
            if imp.imported_name in ("*", ):
                severity = "info"

            evidence = f"import {imp.imported_name}" if not imp.alias else f"import {imp.imported_name} as {imp.alias}"
            smells.append(self._create_smell(
                smell_type="unused_import",
                severity=severity,
                message=f"Import '{imp.imported_name}' appears unused",
                evidence=evidence,
                file_path=file_.file_path,
                start_line=None,
                end_line=None,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(imp.source_file_id),
                symbol_id=str(imp.imported_symbol_id) if imp.imported_symbol_id else None,
            ))
        return smells

    # ── dead code ────────────────────────────────────────────────────

    async def detect_dead_code(
        self, repo_id: str
    ) -> list[CodeSmell]:
        stmt = (
            select(CodeSymbol, CodeFile)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type.in_(["FUNCTION", "METHOD", "CLASS"]),
                CodeSymbol.visibility.in_(["private", "PRIVATE", None]),
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for symbol, file_ in result.all():
            callers_stmt = select(func.count()).where(
                CodeCall.callee_name == symbol.name,
                CodeCall.repository_id == UUID(repo_id),
            )
            callers_result = await self.db.execute(callers_stmt)
            caller_count = callers_result.scalar() or 0

            refs_stmt = select(func.count()).where(
                CodeReference.target_name == symbol.name,
                CodeReference.repository_id == UUID(repo_id),
            )
            refs_result = await self.db.execute(refs_stmt)
            ref_count = refs_result.scalar() or 0

            if caller_count > 0 or ref_count > 0:
                continue

            confidence = 0.65
            severity = "low"
            if symbol.symbol_type == "CLASS":
                confidence = 0.55
                severity = "info"

            evidence = self._get_evidence(
                file_.file_path, symbol.start_line, symbol.end_line, 3,
            )
            smells.append(self._create_smell(
                smell_type="dead_code",
                severity=severity,
                message=f"'{symbol.name}' ({symbol.symbol_type.lower()}) has no callers or references",
                evidence=evidence,
                file_path=file_.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(symbol.file_id),
                symbol_id=str(symbol.id),
            ))
        return smells

    # ── circular dependencies ────────────────────────────────────────

    async def detect_circular_dependencies(
        self, repo_id: str
    ) -> list[CodeSmell]:
        from app.code_intelligence.models import CodeImport

        import_stmt = (
            select(CodeImport, CodeFile)
            .join(CodeFile, CodeImport.source_file_id == CodeFile.id)
            .where(
                CodeImport.repository_id == UUID(repo_id),
                CodeImport.resolved == True,
            )
        )
        result = await self.db.execute(import_stmt)
        edges: dict[str, set[str]] = defaultdict(set)
        file_map: dict[str, tuple[str, str]] = {}

        for imp, file_ in result.all():
            src_path = file_.file_path
            file_map[src_path] = (str(imp.source_file_id), file_.file_path)

            target_sym_stmt = select(CodeSymbol.file_id).where(
                CodeSymbol.id == imp.imported_symbol_id
            )
            target_result = await self.db.execute(target_sym_stmt)
            target_file_id = target_result.scalar()
            if target_file_id:
                target_file_stmt = select(CodeFile.file_path).where(
                    CodeFile.id == target_file_id
                )
                target_result2 = await self.db.execute(target_file_stmt)
                target_path = target_result2.scalar()
                if target_path and target_path != src_path:
                    edges[src_path].add(target_path)

        visited: set[str] = set()
        in_stack: set[str] = set()
        cycles: list[list[str]] = []

        def _dfs(node: str, path: list[str]) -> None:
            if node in in_stack:
                idx = path.index(node)
                cycles.append(path[idx:])
                return
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            path.append(node)
            for neighbor in edges.get(node, set()):
                _dfs(neighbor, path)
            path.pop()
            in_stack.remove(node)

        for node in edges:
            _dfs(node, [])

        smells = []
        for cycle in cycles:
            cycle_display = " -> ".join(cycle) + " -> " + cycle[0]
            severity = "high" if len(cycle) > 3 else "medium"
            confidence = 0.9

            file_id = file_map.get(cycle[0], (None, None))[0]
            smells.append(self._create_smell(
                smell_type="circular_dependency",
                severity=severity,
                message=f"Circular dependency detected: {cycle_display}",
                evidence=cycle_display,
                file_path=cycle[0],
                start_line=None,
                end_line=None,
                confidence=confidence,
                repo_id=repo_id,
                file_id=file_id or "",
                symbol_id=None,
            ))
        return smells

    # ── high coupling ────────────────────────────────────────────────

    async def detect_high_coupling(
        self, repo_id: str, threshold: int | None = None
    ) -> list[CodeSmell]:
        threshold = threshold or self.config["high_coupling_threshold"]
        stmt = (
            select(CodeMetrics, CodeFile)
            .join(CodeFile, CodeMetrics.file_id == CodeFile.id)
            .where(
                CodeMetrics.repository_id == UUID(repo_id),
                CodeMetrics.symbol_id.is_(None),
                (CodeMetrics.fan_in + CodeMetrics.fan_out) > threshold,
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for metrics, file_ in result.all():
            total = metrics.fan_in + metrics.fan_out
            ratio = total / threshold
            confidence = round(min(0.5 + 0.12 * (ratio - 1), 0.95), 2)
            severity = "low"
            if total > threshold * 2:
                severity = "high"
            elif total > threshold * 1.5:
                severity = "medium"

            smells.append(self._create_smell(
                smell_type="high_coupling",
                severity=severity,
                message=(
                    f"File '{file_.file_path}' has coupling score {total} "
                    f"(fan-in: {metrics.fan_in}, fan-out: {metrics.fan_out})"
                ),
                evidence=f"fan-in={metrics.fan_in}, fan-out={metrics.fan_out}, total={total}",
                file_path=file_.file_path,
                start_line=None,
                end_line=None,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(metrics.file_id),
                symbol_id=None,
            ))
        return smells

    # ── low cohesion ─────────────────────────────────────────────────

    async def detect_low_cohesion(
        self, repo_id: str
    ) -> list[CodeSmell]:
        class_stmt = (
            select(CodeSymbol)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type == "CLASS",
            )
        )
        class_result = await self.db.execute(class_stmt)
        classes = class_result.scalars().all()

        smells = []
        for cls in classes:
            methods_stmt = (
                select(CodeSymbol)
                .where(
                    CodeSymbol.repository_id == UUID(repo_id),
                    CodeSymbol.parent_symbol_id == cls.name,
                    CodeSymbol.symbol_type == "METHOD",
                )
            )
            methods_result = await self.db.execute(methods_stmt)
            methods = methods_result.scalars().all()

            if len(methods) < 3:
                continue

            file_stmt = select(CodeFile.file_path).where(CodeFile.id == cls.file_id)
            file_result = await self.db.execute(file_stmt)
            file_path = file_result.scalar() or ""

            shared_names: Counter = Counter()
            for method in methods:
                refs_stmt = (
                    select(CodeReference.target_name)
                    .where(
                        CodeReference.source_file_id == cls.file_id,
                        CodeReference.source_symbol_id == method.id,
                    )
                )
                refs_result = await self.db.execute(refs_stmt)
                targets = refs_result.scalars().all()
                shared_names.update(targets)

            if not shared_names:
                cohesion_score = 0.0
            else:
                most_common_count = shared_names.most_common(1)[0][1]
                cohesion_score = most_common_count / len(methods)

            if cohesion_score > 0.4:
                continue

            confidence = round(max(0.5, 0.9 - cohesion_score), 2)
            severity = "medium" if cohesion_score < 0.2 else "low"

            evidence = self._get_evidence(
                file_path, cls.start_line, cls.end_line, 3,
            )
            smells.append(self._create_smell(
                smell_type="low_cohesion",
                severity=severity,
                message=(
                    f"Class '{cls.name}' has low cohesion "
                    f"({len(methods)} methods, score: {cohesion_score:.2f})"
                ),
                evidence=evidence,
                file_path=file_path,
                start_line=cls.start_line,
                end_line=cls.end_line,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(cls.file_id),
                symbol_id=str(cls.id),
            ))
        return smells

    # ── duplicate patterns ───────────────────────────────────────────

    async def detect_duplicate_patterns(
        self, repo_id: str
    ) -> list[CodeSmell]:
        chunk_size = 5
        stmt = (
            select(CodeSymbol, CodeFile)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type.in_(["FUNCTION", "METHOD"]),
                CodeSymbol.start_line.isnot(None),
                CodeSymbol.end_line.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        symbols = result.all()

        fingerprints: dict[str, list[tuple]] = {}
        for symbol, file_ in symbols:
            if not symbol.start_line or not symbol.end_line:
                continue
            length = symbol.end_line - symbol.start_line
            if length < chunk_size:
                continue

            file_stmt = select(CodeFile.file_path).where(CodeFile.id == symbol.file_id)
            file_result = await self.db.execute(file_stmt)
            path = file_result.scalar()
            if not path:
                continue

            normalized = f"{symbol.name}_{length}_{path}"
            fp = hashlib.md5(normalized.encode()).hexdigest()

            if fp not in fingerprints:
                fingerprints[fp] = []
            fingerprints[fp].append((symbol, file_))

        smells = []
        for fp, group in fingerprints.items():
            if len(group) < 2:
                continue
            seen_pairs: set[tuple[str, str]] = set()
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    sym_a, file_a = group[i]
                    sym_b, file_b = group[j]
                    pair_key = (str(sym_a.id), str(sym_b.id))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    evidence_a = self._get_evidence(
                        file_a.file_path, sym_a.start_line, sym_a.end_line, 3,
                    )
                    evidence_b = self._get_evidence(
                        file_b.file_path, sym_b.start_line, sym_b.end_line, 3,
                    )

                    length = sym_a.end_line - sym_a.start_line
                    confidence = round(min(0.4 + 0.02 * length, 0.85), 2)
                    severity = "medium" if length > 20 else "low"

                    combined_evidence = (
                        f"--- {file_a.file_path}:{sym_a.name} ---\n"
                        f"{evidence_a}\n"
                        f"--- {file_b.file_path}:{sym_b.name} ---\n"
                        f"{evidence_b}"
                    )
                    smells.append(self._create_smell(
                        smell_type="duplicate_pattern",
                        severity=severity,
                        message=(
                            f"Similar patterns in '{sym_a.name}' ({file_a.file_path}) "
                            f"and '{sym_b.name}' ({file_b.file_path})"
                        ),
                        evidence=combined_evidence,
                        file_path=file_a.file_path,
                        start_line=sym_a.start_line,
                        end_line=sym_a.end_line,
                        confidence=confidence,
                        repo_id=repo_id,
                        file_id=str(sym_a.file_id),
                        symbol_id=str(sym_a.id),
                    ))
        return smells

    # ── long files ───────────────────────────────────────────────────

    async def detect_long_files(
        self, repo_id: str, threshold: int | None = None
    ) -> list[CodeSmell]:
        threshold = threshold or self.config["large_file_threshold"]
        stmt = (
            select(CodeMetrics, CodeFile)
            .join(CodeFile, CodeMetrics.file_id == CodeFile.id)
            .where(
                CodeMetrics.repository_id == UUID(repo_id),
                CodeMetrics.symbol_id.is_(None),
                CodeMetrics.loc > threshold,
            )
        )
        result = await self.db.execute(stmt)
        smells = []
        for metrics, file_ in result.all():
            loc = metrics.loc or 0
            ratio = loc / threshold
            confidence = round(min(0.55 + 0.15 * (ratio - 1), 0.95), 2)
            severity = "low"
            if loc > threshold * 2:
                severity = "high"
            elif loc > threshold * 1.5:
                severity = "medium"

            smells.append(self._create_smell(
                smell_type="long_file",
                severity=severity,
                message=f"File '{file_.file_path}' is {loc} lines (threshold: {threshold})",
                evidence=f"Total lines: {loc}, code: {metrics.code_lines}, comments: {metrics.comment_lines}",
                file_path=file_.file_path,
                start_line=None,
                end_line=None,
                confidence=confidence,
                repo_id=repo_id,
                file_id=str(metrics.file_id),
                symbol_id=None,
            ))
        return smells

    # ── helpers ──────────────────────────────────────────────────────

    def _create_smell(
        self,
        smell_type: str,
        severity: str,
        message: str,
        evidence: str,
        file_path: str,
        start_line: Optional[int],
        end_line: Optional[int],
        confidence: float,
        repo_id: str,
        file_id: str,
        symbol_id: Optional[str],
    ) -> CodeSmell:
        suggested_fix = self._suggest_fix(smell_type, message)
        return CodeSmell(
            repository_id=UUID(repo_id),
            file_id=UUID(file_id),
            symbol_id=UUID(symbol_id) if symbol_id else None,
            smell_type=smell_type,
            severity=severity,
            message=message,
            evidence=evidence,
            suggested_fix=suggested_fix,
            confidence=confidence,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            detected_at=datetime.now(timezone.utc),
        )

    def _get_evidence(
        self,
        file_path: str,
        start_line: Optional[int],
        end_line: Optional[int],
        context_lines: int,
    ) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except (OSError, IOError):
            return f"[unable to read {file_path}]"

        if start_line is None:
            return ""

        start = max(0, (start_line or 1) - 1)
        end = min(len(all_lines), (end_line or start_line or 1) + context_lines)
        snippet = "".join(all_lines[start:end])
        return snippet.strip()

    def _suggest_fix(self, smell_type: str, message: str) -> str:
        suggestions = {
            "long_function": "Consider extracting helper functions or splitting into smaller responsibilities.",
            "god_class": "Apply the Single Responsibility Principle — split into focused classes.",
            "deep_nesting": "Reduce nesting by using early returns, guard clauses, or extracting inner logic.",
            "large_parameter_list": "Group related parameters into a config/data object or use keyword arguments.",
            "unused_import": "Remove the unused import to reduce clutter and potential import errors.",
            "dead_code": "Remove dead code or mark it as public if it is part of the module API.",
            "circular_dependency": "Introduce an interface module, use dependency injection, or invert the dependency.",
            "high_coupling": "Reduce direct dependencies by introducing abstractions or event-based communication.",
            "low_cohesion": "Group related methods into smaller, focused classes.",
            "duplicate_pattern": "Extract common logic into a shared utility function or base class.",
            "long_file": "Split into smaller files organized by responsibility or feature.",
        }
        return suggestions.get(smell_type, "Review and refactor as needed.")

    async def get_smell_summary(self, repo_id: str) -> dict:
        stmt = (
            select(CodeSmell)
            .where(CodeSmell.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        smells = result.scalars().all()

        by_type: dict[str, int] = Counter()
        by_severity: dict[str, int] = Counter()
        total = 0

        for smell in smells:
            by_type[smell.smell_type] += 1
            by_severity[smell.severity] += 1
            total += 1

        return {
            "repository_id": repo_id,
            "total_smells": total,
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "avg_confidence": (
                round(sum(s.confidence for s in smells) / total, 2)
                if total > 0
                else 0.0
            ),
        }
