"""Code Quality Intelligence — cyclomatic complexity, maintainability index, trend analysis."""

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class ComplexityItem:
    file: str
    line: int
    name: str
    type: str  # function, method, class
    cyclomatic_complexity: int
    cognitive_complexity: int = 0
    lines_of_code: int = 0


@dataclass
class MaintainabilityScore:
    file: str
    maintainability_index: float  # 0-100
    halstead_volume: float = 0.0
    cyclomatic_sum: int = 0
    lines_of_code: int = 0
    comment_ratio: float = 0.0


@dataclass
class CodeQualitySnapshot:
    repo_id: str
    timestamp: str
    complexity: list[ComplexityItem] = field(default_factory=list)
    maintainability: list[MaintainabilityScore] = field(default_factory=list)
    avg_complexity: float = 0.0
    high_complexity_count: int = 0
    avg_maintainability: float = 0.0
    low_maintainability_count: int = 0
    tech_debt_ratio: float = 0.0  # estimated hours
    total_functions: int = 0
    total_classes: int = 0


@dataclass
class QualityTrend:
    date: str
    avg_complexity: float
    avg_maintainability: float
    tech_debt_hours: float
    function_count: int
    high_complexity_pct: float


class ComplexityAnalyzer(ast.NodeVisitor):
    """Computes cyclomatic and cognitive complexity of Python code."""

    def __init__(self):
        self.complexity = 1
        self.cognitive = 0
        self.nesting = 0
        self.functions: list[tuple[str, int, int, int]] = []
        self.current_function = None

    def visit_FunctionDef(self, node):
        old_complexity = self.complexity
        old_cognitive = self.cognitive
        old_nesting = self.nesting
        old_fn = self.current_function
        self.complexity = 1
        self.cognitive = 0
        self.nesting = 0
        self.current_function = node.name
        self.generic_visit(node)
        end_lineno = getattr(node, 'end_lineno', node.lineno) or node.lineno
        loc = end_lineno - node.lineno + 1
        self.functions.append((node.name, node.lineno, self.complexity, loc))
        self.complexity = old_complexity
        self.cognitive = old_cognitive
        self.nesting = old_nesting
        self.current_function = old_fn

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def _visit_branching(self, node):
        self.complexity += 1
        self.cognitive += 1 + self.nesting

    def visit_If(self, node):
        self._visit_branching(node)
        self.nesting += 1
        self.generic_visit(node)
        self.nesting -= 1

    def visit_While(self, node):
        self._visit_branching(node)
        self.nesting += 1
        self.generic_visit(node)
        self.nesting -= 1

    def visit_For(self, node):
        self.complexity += 1
        self.cognitive += 1 + self.nesting
        self.nesting += 1
        self.generic_visit(node)
        self.nesting -= 1

    def visit_AsyncFor(self, node):
        self.visit_For(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.cognitive += 1

    def visit_BoolOp(self, node):
        self.complexity += len(node.values) - 1
        self.cognitive += len(node.values) - 1

    def visit_Assert(self, node):
        self.complexity += 1

    def visit_Ternary(self, node):
        self.complexity += 1
        self.cognitive += 1 + self.nesting


class CodeQualityService:
    """Tracks cyclomatic complexity, maintainability index, and trend analysis."""

    _history: dict[str, list[CodeQualitySnapshot]] = defaultdict(list)

    @staticmethod
    def analyze_file(file_path: Path) -> Optional[dict[str, Any]]:
        if file_path.suffix != ".py":
            return None
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)

            analyzer = ComplexityAnalyzer()
            analyzer.visit(tree)

            loc = content.count("\n") + 1
            comment_lines = len([l for l in content.split("\n") if l.strip().startswith("#")])
            comment_ratio = comment_lines / max(loc, 1)

            halstead_operators = len(re.findall(r'[+\-*/%=<>!&|^~]+', content))
            halstead_operands = len(re.findall(r'\b[a-zA-Z_]\w*\b', content))
            halstead_vocab = halstead_operators + halstead_operands
            halstead_length = sum(len(m.group()) for m in re.finditer(r'[+\-*/%=<>!&|^~]+|\b[a-zA-Z_]\w*\b', content))
            halstead_volume = 0
            if halstead_vocab > 0:
                halstead_volume = halstead_length * (halstead_vocab.bit_length() or 1)

            total_complexity = sum(f[2] for f in analyzer.functions)
            mi = 100.0
            if analyzer.functions:
                avg_comp = total_complexity / len(analyzer.functions)
                mi = max(0, 171 - 5.2 * (halstead_volume ** 0.5 or 1) - 0.23 * avg_comp - 16.2 * (loc ** 0.5))
                mi = min(100, mi * 100 / 171)

            return {
                "file": str(file_path),
                "functions": [
                    {"name": f[0], "line": f[1], "complexity": f[2], "loc": f[3]}
                    for f in analyzer.functions
                ],
                "total_functions": len(analyzer.functions),
                "total_loc": loc,
                "comment_ratio": round(comment_ratio, 3),
                "avg_complexity": round(total_complexity / max(len(analyzer.functions), 1), 2),
                "halstead_volume": round(halstead_volume, 2),
                "maintainability_index": round(mi, 2),
            }
        except SyntaxError:
            return None
        except Exception:
            return None

    @staticmethod
    def analyze_repository(repo_path: str) -> CodeQualitySnapshot:
        path = Path(repo_path)
        snapshot = CodeQualitySnapshot(
            repo_id=str(hash(str(path))),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        for file_path in sorted(path.rglob("*.py")):
            if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".git", "venv", ".venv")
                   for p in file_path.parts):
                continue
            result = CodeQualityService.analyze_file(file_path)
            if result:
                for fn in result["functions"]:
                    snapshot.complexity.append(ComplexityItem(
                        file=result["file"],
                        line=fn["line"],
                        name=fn["name"],
                        type="function",
                        cyclomatic_complexity=fn["complexity"],
                        lines_of_code=fn["loc"],
                    ))
                snapshot.maintainability.append(MaintainabilityScore(
                    file=result["file"],
                    maintainability_index=result["maintainability_index"],
                    halstead_volume=result["halstead_volume"],
                    cyclomatic_sum=result["avg_complexity"] * result["total_functions"],
                    lines_of_code=result["total_loc"],
                    comment_ratio=result["comment_ratio"],
                ))

        if snapshot.complexity:
            snapshot.avg_complexity = sum(
                c.cyclomatic_complexity for c in snapshot.complexity
            ) / len(snapshot.complexity)
            snapshot.high_complexity_count = sum(
                1 for c in snapshot.complexity if c.cyclomatic_complexity > 10
            )

        if snapshot.maintainability:
            snapshot.avg_maintainability = sum(
                m.maintainability_index for m in snapshot.maintainability
            ) / len(snapshot.maintainability)
            snapshot.low_maintainability_count = sum(
                1 for m in snapshot.maintainability if m.maintainability_index < 50
            )

        snapshot.total_functions = len(snapshot.complexity)
        snapshot.total_classes = sum(
            1 for c in snapshot.complexity if c.type == "class"
        )

        debt_hours = sum(
            (c.cyclomatic_complexity - 5) * 0.5
            for c in snapshot.complexity
            if c.cyclomatic_complexity > 5
        )
        snapshot.tech_debt_ratio = round(debt_hours, 2)

        CodeQualityService._history[snapshot.repo_id].append(snapshot)
        if len(CodeQualityService._history[snapshot.repo_id]) > 100:
            CodeQualityService._history[snapshot.repo_id] = (
                CodeQualityService._history[snapshot.repo_id][-100:]
            )

        return snapshot

    @staticmethod
    def get_trends(repo_id: str) -> list[QualityTrend]:
        snapshots = CodeQualityService._history.get(repo_id, [])
        return [
            QualityTrend(
                date=s.timestamp[:10],
                avg_complexity=s.avg_complexity,
                avg_maintainability=s.avg_maintainability,
                tech_debt_hours=s.tech_debt_ratio,
                function_count=s.total_functions,
                high_complexity_pct=round(
                    s.high_complexity_count / max(s.total_functions, 1) * 100, 1
                ),
            )
            for s in snapshots[-30:]
        ]


code_quality = CodeQualityService()
