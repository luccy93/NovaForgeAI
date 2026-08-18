"""Code Metrics Calculator — McCabe, cognitive complexity, maintainability, Halstead."""

import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeCall,
    CodeFile,
    CodeMetrics,
    CodeSymbol,
)

logger = logging.getLogger(__name__)


class MetricsCalculator:
    """Calculate and store software metrics for files and symbols."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ── public API ───────────────────────────────────────────────────

    async def calculate_file_metrics(
        self,
        file_id: str,
        content: str,
        language: str,
        symbols: list,
        repo_id: str,
    ) -> CodeMetrics:
        loc = self._count_loc(content)
        cc = self._cyclomatic_complexity(content, language)
        cog = self._cognitive_complexity(content, language)
        nest = self._nesting_depth(content, language)
        hal = self._halstead_volume(content)
        mi = self._maintainability_index(loc["loc"], cc, hal)
        fan_in, fan_out = await self._fan_in_fan_out_file(file_id)
        dep_count = await self._dependency_count_file(file_id)

        metrics = CodeMetrics(
            file_id=UUID(file_id),
            symbol_id=None,
            repository_id=UUID(repo_id),
            loc=loc["loc"],
            code_lines=loc["code_lines"],
            comment_lines=loc["comment_lines"],
            blank_lines=loc["blank_lines"],
            cyclomatic_complexity=cc,
            cognitive_complexity=cog,
            function_length=None,
            class_size=None,
            nesting_depth=nest,
            parameter_count=self._parameter_count(content, language),
            dependency_count=dep_count,
            fan_in=fan_in,
            fan_out=fan_out,
            maintainability_index=mi,
            halstead_volume=hal,
            calculated_at=datetime.now(timezone.utc),
        )
        self.db.add(metrics)
        await self.db.flush()
        return metrics

    async def calculate_symbol_metrics(
        self,
        symbol_id: str,
        content: str,
        language: str,
        file_id: str,
        repo_id: str,
    ) -> CodeMetrics:
        loc = self._count_loc(content)
        cc = self._cyclomatic_complexity(content, language)
        cog = self._cognitive_complexity(content, language)
        nest = self._nesting_depth(content, language)
        hal = self._halstead_volume(content)
        mi = self._maintainability_index(loc["loc"], cc, hal)
        fan_in, fan_out = await self._fan_in_fan_out(symbol_id)

        metrics = CodeMetrics(
            file_id=UUID(file_id),
            symbol_id=UUID(symbol_id),
            repository_id=UUID(repo_id),
            loc=loc["loc"],
            code_lines=loc["code_lines"],
            comment_lines=loc["comment_lines"],
            blank_lines=loc["blank_lines"],
            cyclomatic_complexity=cc,
            cognitive_complexity=cog,
            function_length=loc["code_lines"],
            class_size=None,
            nesting_depth=nest,
            parameter_count=self._parameter_count(content, language),
            dependency_count=0,
            fan_in=fan_in,
            fan_out=fan_out,
            maintainability_index=mi,
            halstead_volume=hal,
            calculated_at=datetime.now(timezone.utc),
        )
        self.db.add(metrics)
        await self.db.flush()
        return metrics

    async def calculate_repository_metrics(
        self, repo_id: str, index_id: str
    ) -> dict:
        stmt = select(CodeMetrics).where(
            CodeMetrics.repository_id == UUID(repo_id),
            CodeMetrics.symbol_id.is_(None),
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {
                "total_files": 0,
                "total_loc": 0,
                "avg_complexity": 0.0,
                "avg_maintainability": 0.0,
                "max_complexity": 0,
                "min_maintainability": 100.0,
                "total_code_lines": 0,
                "total_comment_lines": 0,
                "total_blank_lines": 0,
            }

        total_loc = sum(r.loc or 0 for r in rows)
        total_code = sum(r.code_lines or 0 for r in rows)
        total_comment = sum(r.comment_lines or 0 for r in rows)
        total_blank = sum(r.blank_lines or 0 for r in rows)
        complexities = [r.cyclomatic_complexity or 0 for r in rows]
        mi_values = [
            r.maintainability_index for r in rows
            if r.maintainability_index is not None
        ]

        return {
            "total_files": len(rows),
            "total_loc": total_loc,
            "total_code_lines": total_code,
            "total_comment_lines": total_comment,
            "total_blank_lines": total_blank,
            "avg_complexity": (
                sum(complexities) / len(complexities) if complexities else 0.0
            ),
            "max_complexity": max(complexities) if complexities else 0,
            "avg_maintainability": (
                sum(mi_values) / len(mi_values) if mi_values else 0.0
            ),
            "min_maintainability": min(mi_values) if mi_values else 100.0,
        }

    # ── LOC counting ────────────────────────────────────────────────

    def _count_loc(self, content: str) -> dict:
        lines = content.splitlines()
        total = len(lines)
        blank = 0
        comment = 0
        in_block = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank += 1
                continue
            if in_block:
                comment += 1
                if "*/" in stripped:
                    in_block = False
                continue
            if stripped.startswith("//"):
                comment += 1
                continue
            if stripped.startswith("#"):
                comment += 1
                continue
            if stripped.startswith("/*"):
                comment += 1
                if "*/" not in stripped or stripped.endswith("*/") and stripped.count("/*") > stripped.count("*/"):
                    in_block = True
                continue

        code = total - blank - comment
        return {
            "loc": total,
            "code_lines": max(code, 0),
            "comment_lines": comment,
            "blank_lines": blank,
        }

    # ── Cyclomatic complexity (regex-based) ──────────────────────────

    def _cyclomatic_complexity(self, content: str, language: str) -> int:
        cc = 1
        branch_kw = {
            "if", "else if", "elif", "elsif",
            "for", "foreach", "while", "do",
            "case", "catch", "except", "when",
            "and", "or", "&&", "||",
            "match",
        }
        lines = content.splitlines()
        in_block_comment = False

        for line in lines:
            stripped = line.strip()
            if in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                continue
            if stripped.startswith("/*"):
                if "*/" not in stripped or stripped.count("/*") > stripped.count("*/"):
                    in_block_comment = True
                continue
            if stripped.startswith("//") or stripped.startswith("#"):
                continue

            lower = stripped.lower()
            for kw in branch_kw:
                pattern = rf"\b{re.escape(kw)}\b"
                cc += len(re.findall(pattern, lower))

        return max(cc, 1)

    # ── Cognitive complexity (best-effort regex) ─────────────────────

    def _cognitive_complexity(self, content: str, language: str) -> int:
        score = 0
        lines = content.splitlines()
        in_block_comment = False
        nesting_stack: list[int] = []
        current_indent = 0

        for line in lines:
            stripped = line.strip()
            if in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                continue
            if stripped.startswith("/*"):
                if "*/" not in stripped or stripped.count("/*") > stripped.count("*/"):
                    in_block_comment = True
                continue
            if stripped.startswith("//") or stripped.startswith("#"):
                continue

            raw_indent = len(line) - len(line.lstrip())
            if nesting_stack:
                while nesting_stack and raw_indent <= nesting_stack[-1]:
                    nesting_stack.pop()

            lower = stripped.lower()

            nesting_increments = 0
            for kw in ("if ", "if(", "elif ", "elsif ", "else if ", "when "):
                if lower.startswith(kw) or f" {kw}" in lower:
                    nesting_increments += 1
                    break
            for kw in ("for ", "foreach ", "while ", "do "):
                if lower.startswith(kw) or f" {kw}" in lower:
                    nesting_increments += 1
                    break
            if lower.startswith("switch ") or lower.startswith("match "):
                nesting_increments += 1

            if nesting_increments > 0:
                current_nesting = len(nesting_stack) + 1
                score += current_nesting
                nesting_stack.append(raw_indent)

            for kw in ("break", "continue", "return", "yield", "raise", "throw"):
                if rf"\b{kw}\b" in lower:
                    score += 1

            if "&&" in stripped or "||" in stripped:
                score += max(lower.count("&&"), lower.count("||"))

            if lower.startswith("else"):
                score += 1

        return max(score, 0)

    # ── Nesting depth ───────────────────────────────────────────────

    def _nesting_depth(self, content: str, language: str) -> int:
        max_depth = 0
        current = 0
        in_string = False
        in_block_comment = False
        in_line_comment = False
        escape = False
        block_depth = 0

        for ch in content:
            if in_block_comment:
                if ch == "/" and current > 0:
                    pass
                if ch == "*":
                    in_block_comment = False
                continue
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                continue
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if in_string:
                if ch == '"':
                    in_string = False
                continue

            if ch == "/" and current > 0:
                in_line_comment = True
                continue

            if ch in ("{", "(", "["):
                current += 1
                if current > max_depth:
                    max_depth = current
            elif ch in ("}", ")", "]"):
                current = max(current - 1, 0)

        return max_depth

    # ── Parameter count ─────────────────────────────────────────────

    def _parameter_count(self, content: str, language: str) -> int:
        patterns = [
            r"def\s+\w+\s*\(([^)]*)\)",
            r"function\s+\w+\s*\(([^)]*)\)",
            r"\w+\s*\(([^)]*)\)\s*[:{]",
        ]
        max_params = 0
        for pat in patterns:
            for match in re.finditer(pat, content):
                params_str = match.group(1).strip()
                if not params_str:
                    continue
                params = [p.strip() for p in params_str.split(",") if p.strip()]
                max_params = max(max_params, len(params))
        return max_params

    # ── Fan-in / Fan-out (async, per symbol) ────────────────────────

    async def _fan_in_fan_out(self, symbol_id: str) -> tuple[int, int]:
        sym_uuid = UUID(symbol_id)

        fan_out_stmt = select(func.count()).where(
            CodeCall.caller_symbol_id == sym_uuid
        )
        fan_out_result = await self.db.execute(fan_out_stmt)
        fan_out = fan_out_result.scalar() or 0

        fan_in_stmt = select(func.count()).where(
            CodeCall.callee_symbol_id == sym_uuid
        )
        fan_in_result = await self.db.execute(fan_in_stmt)
        fan_in = fan_in_result.scalar() or 0

        return fan_in, fan_out

    async def _fan_in_fan_out_file(self, file_id: str) -> tuple[int, int]:
        file_uuid = UUID(file_id)

        fan_out_stmt = select(func.count()).where(
            CodeCall.caller_file_id == file_uuid
        )
        fan_out_result = await self.db.execute(fan_out_stmt)
        fan_out = fan_out_result.scalar() or 0

        fan_in_stmt = (
            select(func.count())
            .join(CodeFile, CodeFile.id == CodeCall.caller_file_id)
            .where(
                CodeCall.caller_file_id == file_uuid,
            )
        )
        fan_in_result = await self.db.execute(fan_in_stmt)
        fan_in = fan_in_result.scalar() or 0

        return fan_in, fan_out

    async def _dependency_count_file(self, file_id: str) -> int:
        from app.code_intelligence.models import CodeImport

        stmt = select(func.count()).where(
            CodeImport.source_file_id == UUID(file_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ── Maintainability index ───────────────────────────────────────

    def _maintainability_index(
        self, loc: int, cc: int, halstead: float
    ) -> float:
        if loc == 0:
            return 100.0
        raw = (
            171
            - 5.2 * math.log(max(loc, 1))
            - 0.23 * cc
            - 16.2 * math.log(max(halstead, 1.0))
        )
        mi = max(0.0, raw * 100.0 / 171.0)
        return round(mi, 2)

    # ── Halstead volume ─────────────────────────────────────────────

    def _halstead_volume(self, content: str) -> float:
        operators = set()
        operands = set()
        op_count = 0
        operand_count = 0

        op_tokens = re.findall(
            r"[+\-*/%=!<>&|^~?:]+|\b(?:and|or|not|is|in|as|del)\b", content
        )
        for t in op_tokens:
            operators.add(t)
            op_count += 1

        word_tokens = re.findall(r"\b[a-zA-Z_]\w*\b", content)
        for t in word_tokens:
            if t.lower() in (
                "if", "else", "for", "while", "do", "switch", "case",
                "break", "continue", "return", "class", "def", "function",
                "var", "let", "const", "try", "catch", "finally", "throw",
                "new", "this", "self", "true", "false", "null", "None",
                "void", "async", "await", "yield", "import", "export",
                "from", "with", "as", "lambda", "pass", "raise",
            ):
                continue
            operands.add(t)
            operand_count += 1

        num_operators = max(len(operators), 1)
        num_operands = max(len(operands), 1)
        n1 = max(op_count, 1)
        n2 = max(operand_count, 1)
        vocab = num_operators + num_operands
        length = n1 + n2

        if vocab <= 1:
            return 0.0

        volume = length * math.log2(vocab)
        return round(volume, 2)

    # ── Threshold flagging ──────────────────────────────────────────

    async def flag_high_complexity(
        self, repo_id: str, threshold: int = 10
    ) -> list[dict]:
        stmt = (
            select(CodeMetrics, CodeSymbol, CodeFile)
            .join(CodeSymbol, CodeMetrics.symbol_id == CodeSymbol.id, isouter=True)
            .join(CodeFile, CodeMetrics.file_id == CodeFile.id)
            .where(
                CodeMetrics.repository_id == UUID(repo_id),
                CodeMetrics.symbol_id.isnot(None),
                CodeMetrics.cyclomatic_complexity > threshold,
            )
        )
        result = await self.db.execute(stmt)
        flagged = []
        for metrics, symbol, file_ in result.all():
            flagged.append({
                "symbol_id": str(metrics.symbol_id),
                "symbol_name": symbol.name if symbol else "unknown",
                "file_path": file_.file_path if file_ else "",
                "cyclomatic_complexity": metrics.cyclomatic_complexity,
                "file_id": str(metrics.file_id),
            })
        return flagged

    async def flag_deep_nesting(
        self, repo_id: str, threshold: int = 5
    ) -> list[dict]:
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
        flagged = []
        for metrics, symbol, file_ in result.all():
            flagged.append({
                "symbol_id": str(metrics.symbol_id) if metrics.symbol_id else None,
                "symbol_name": symbol.name if symbol else file_.file_name,
                "file_path": file_.file_path if file_ else "",
                "nesting_depth": metrics.nesting_depth,
                "file_id": str(metrics.file_id),
            })
        return flagged

    async def flag_large_files(
        self, repo_id: str, threshold: int = 500
    ) -> list[dict]:
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
        flagged = []
        for metrics, file_ in result.all():
            flagged.append({
                "file_id": str(metrics.file_id),
                "file_path": file_.file_path,
                "loc": metrics.loc,
                "code_lines": metrics.code_lines,
            })
        return flagged

    async def flag_high_coupling(
        self, repo_id: str, threshold: int = 20
    ) -> list[dict]:
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
        flagged = []
        for metrics, file_ in result.all():
            flagged.append({
                "file_id": str(metrics.file_id),
                "file_path": file_.file_path,
                "fan_in": metrics.fan_in,
                "fan_out": metrics.fan_out,
                "total_coupling": metrics.fan_in + metrics.fan_out,
            })
        return flagged

    async def get_maintainability_report(self, repo_id: str) -> dict:
        repo_metrics = await self.calculate_repository_metrics(repo_id, "")
        high_complexity = await self.flag_high_complexity(repo_id)
        deep_nesting = await self.flag_deep_nesting(repo_id)
        large_files = await self.flag_large_files(repo_id)
        high_coupling = await self.flag_high_coupling(repo_id)

        return {
            "repository_id": repo_id,
            "summary": repo_metrics,
            "high_complexity_symbols": high_complexity,
            "deep_nesting_symbols": deep_nesting,
            "large_files": large_files,
            "high_coupling_files": high_coupling,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
