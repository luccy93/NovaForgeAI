"""Autonomous Refactoring Engine — recommends and plans refactoring operations with risk estimation."""

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class RefactoringOperation:
    id: str
    category: str  # extract_method, extract_class, split_module, reduce_complexity, optimize_imports, remove_dead_code, simplify_logic, improve_readability
    file: str
    line: int = 0
    description: str = ""
    motivation: str = ""
    effort_hours: float = 0.0
    risk: str = "medium"  # low, medium, high
    confidence: float = 0.0
    affected_symbols: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    expected_improvement: str = ""
    rollback_plan: str = ""


@dataclass
class MigrationPlan:
    operations: list[RefactoringOperation] = field(default_factory=list)
    total_effort_hours: float = 0.0
    overall_risk: str = "medium"
    estimated_regression_risk: float = 0.0
    recommended_order: list[str] = field(default_factory=list)


class AutonomousRefactoring:
    """Recommends and plans refactoring operations with effort estimation, risk assessment, and migration plans."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> MigrationPlan:
        plan = MigrationPlan()

        self._recommend_extract_method(plan)
        self._recommend_extract_class(plan)
        self._recommend_split_module(plan)
        self._recommend_reduce_complexity(plan)
        self._recommend_optimize_imports(plan)
        self._recommend_remove_dead_code(plan)
        self._recommend_simplify_logic(plan)

        plan.operations.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x.risk], -x.confidence))
        plan.total_effort_hours = sum(o.effort_hours for o in plan.operations)
        plan.overall_risk = self._overall_risk(plan.operations)
        plan.estimated_regression_risk = self._estimate_regression(plan.operations)
        plan.recommended_order = [o.id for o in plan.operations[:20]]

        return plan

    def _recommend_extract_method(self, plan: MigrationPlan):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, 'end_lineno', node.lineno) or node.lineno
                    fn_lines = end - node.lineno

                    complexity = 1
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.AsyncFor)):
                            complexity += 1
                        elif isinstance(child, ast.BoolOp):
                            complexity += len(child.values) - 1

                    if fn_lines > 30 or complexity > 8:
                        op_id = self._oid("extract_method", rel, node.name)
                        risk = "low" if complexity < 12 else "medium"
                        plan.operations.append(RefactoringOperation(
                            id=op_id,
                            category="extract_method",
                            file=rel,
                            line=node.lineno,
                            description=f"Extract method `{node.name}` ({fn_lines} lines, complexity {complexity})",
                            motivation=f"Method length ({fn_lines} lines) and complexity ({complexity}) exceed recommended thresholds",
                            effort_hours=fn_lines / 50,
                            risk=risk,
                            confidence=min(0.9, complexity / 15),
                            affected_symbols=[node.name],
                            steps=[
                                f"Identify logical blocks within `{node.name}`",
                                "Extract each block into a well-named helper function",
                                "Replace extracted blocks with function calls",
                                f"Add docstrings to new functions",
                                f"Write tests for extracted functions",
                                "Run existing tests to verify correctness",
                            ],
                            expected_improvement=f"Reduce method length from {fn_lines} to ~20 lines, improve readability and testability",
                            rollback_plan="Reverse the extraction: inline extracted functions back into original method",
                        ))

    def _recommend_extract_class(self, plan: MigrationPlan):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    end = getattr(node, 'end_lineno', node.lineno) or node.lineno
                    cls_lines = end - node.lineno

                    if len(methods) > 12 or cls_lines > 400:
                        op_id = self._oid("extract_class", rel, node.name)
                        risk = "high" if len(methods) > 20 else "medium"
                        plan.operations.append(RefactoringOperation(
                            id=op_id,
                            category="extract_class",
                            file=rel,
                            line=node.lineno,
                            description=f"Extract class `{node.name}` ({len(methods)} methods, ~{cls_lines} lines)",
                            motivation=f"Class has {len(methods)} methods spanning {cls_lines} lines — violates Single Responsibility Principle",
                            effort_hours=len(methods) * 0.5,
                            risk=risk,
                            confidence=min(0.85, len(methods) / 25),
                            affected_symbols=[node.name],
                            steps=[
                                f"Analyze responsibilities of `{node.name}`",
                                "Identify cohesive method groups by concern",
                                f"Extract each group into a new focused class",
                                "Add composition/delegation in the original class",
                                "Update all consumer references",
                                "Run full test suite",
                            ],
                            expected_improvement=f"Split {len(methods)} methods across ~{max(2, len(methods) // 6)} focused classes, improving maintainability",
                            rollback_plan="Merge extracted classes back into original class, revert consumer references",
                        ))

    def _recommend_split_module(self, plan: MigrationPlan):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
            except Exception:
                continue

            if lines > 1000:
                rel = str(f.relative_to(self.repo_path))
                op_id = self._oid("split_module", rel, rel)
                risk = "high" if lines > 2000 else "medium"
                plan.operations.append(RefactoringOperation(
                    id=op_id,
                    category="split_module",
                    file=rel,
                    description=f"Split module `{rel}` ({lines} lines)",
                    motivation=f"Module has {lines} lines — exceeds recommended maximum of 500 lines",
                    effort_hours=lines / 100,
                    risk=risk,
                    confidence=0.8,
                    affected_symbols=[rel],
                    steps=[
                        f"Analyze module `{rel}` for cohesive sections",
                        "Create separate modules for each concern",
                        "Move related functions/classes to new modules",
                        "Update imports across the codebase",
                        "Add __init__.py exports if needed",
                        "Run full test suite to verify no broken imports",
                    ],
                    expected_improvement=f"Reduce module from {lines} to ~300 lines per module, improving navigation and maintainability",
                    rollback_plan="Restore original module, revert all import changes",
                ))

    def _recommend_reduce_complexity(self, plan: MigrationPlan):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = 1
                    nesting_depth = 0
                    max_nesting = 0
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith)):
                            complexity += 1
                            nesting_depth += 1
                            max_nesting = max(max_nesting, nesting_depth)
                        elif isinstance(child, ast.BoolOp):
                            complexity += len(child.values) - 1
                        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child != node:
                            pass

                    if complexity > 10 or max_nesting > 4:
                        op_id = self._oid("reduce_complexity", rel, node.name)
                        plan.operations.append(RefactoringOperation(
                            id=op_id,
                            category="reduce_complexity",
                            file=rel,
                            line=node.lineno,
                            description=f"Reduce complexity of `{node.name}` (cyclomatic: {complexity}, max nesting: {max_nesting})",
                            motivation=f"Cyclomatic complexity ({complexity}) exceeds recommended limit of 10",
                            effort_hours=complexity / 5,
                            risk="medium" if complexity < 15 else "high",
                            confidence=min(0.9, complexity / 20),
                            affected_symbols=[node.name],
                            steps=[
                                f"Review function `{node.name}` for simplification opportunities",
                                "Apply early returns / guard clauses to reduce nesting",
                                "Extract complex conditionals into helper functions",
                                "Replace switch/if chains with dictionary dispatch or pattern matching",
                                "Simplify boolean expressions using De Morgan's laws",
                                "Run all tests to verify behavior preservation",
                            ],
                            expected_improvement=f"Reduce cyclomatic complexity from {complexity} to under 10, max nesting from {max_nesting} to under 3",
                            rollback_plan="Revert changes to the function to its original implementation",
                        ))

    def _recommend_optimize_imports(self, plan: MigrationPlan):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            wildcard_imports = re.findall(r'^\s*from\s+\S+\s+import\s+\*', content, re.MULTILINE)
            unused_imports = []
            imported_names = set()
            used_names = set()

            for match in re.finditer(r'^\s*(?:from\s+(\S+)\s+import\s+(\S+)|import\s+(\S+))', content, re.MULTILINE):
                if match.group(2):
                    imported_names.add(match.group(2))
                elif match.group(3):
                    imported_names.add(match.group(3).split(" as ")[0])

            for name in ast.walk(self._try_parse(content) or ast.Module(body=[])):
                if isinstance(name, ast.Name):
                    used_names.add(name.id)

            for imp in imported_names:
                if imp not in used_names:
                    unused_imports.append(imp)

            if wildcard_imports or unused_imports:
                op_id = self._oid("optimize_imports", rel, rel)
                plan.operations.append(RefactoringOperation(
                    id=op_id,
                    category="optimize_imports",
                    file=rel,
                    description=f"Optimize imports in `{rel}` ({len(wildcard_imports)} wildcard, {len(unused_imports)} unused)",
                    motivation=f"File contains wildcard imports and/or unused imports that slow module loading",
                    effort_hours=0.5,
                    risk="low",
                    confidence=0.85,
                    affected_symbols=[rel],
                    steps=[
                        f"Replace wildcard imports in {rel} with specific imports",
                        f"Remove {len(unused_imports)} unused imports",
                        "Sort imports according to project convention (isort, reorder-python-imports)",
                        "Verify no import errors after changes",
                    ],
                    expected_improvement="Faster module loading, clearer dependency visibility, reduced merge conflicts",
                    rollback_plan="Restore original import statements",
                ))

    def _recommend_remove_dead_code(self, plan: MigrationPlan):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            defined = set()
            called = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defined.add(node.name)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node, ast.ClassDef):
                    defined.add(node.name)

            dead = defined - called
            dead = {d for d in dead if not d.startswith("__")}

            if dead:
                op_id = self._oid("remove_dead_code", rel, rel)
                plan.operations.append(RefactoringOperation(
                    id=op_id,
                    category="remove_dead_code",
                    file=rel,
                    description=f"Remove dead code from `{rel}` ({len(dead)} symbols)",
                    motivation=f"Found {len(dead)} defined but apparently unused symbols",
                    effort_hours=len(dead) * 0.25,
                    risk="low",
                    confidence=0.6,
                    affected_symbols=list(dead)[:10],
                    steps=[
                        f"Review each potentially dead symbol in {rel}",
                        f"Verify {', '.join(list(dead)[:5])}{'...' if len(dead) > 5 else ''} are truly unused across the codebase",
                        "Remove dead functions, classes, and variables",
                        "Run full test suite to detect any missed references",
                        "Remove associated imports and comments",
                    ],
                    expected_improvement=f"Reduce codebase size by removing {len(dead)} unused symbols, improving readability",
                    rollback_plan="Restore removed code from version control",
                ))

    def _recommend_simplify_logic(self, plan: MigrationPlan):
        simplification_patterns = [
            (r'(?:if\s+\w+\s*!=\s*None\s*:)|(?:if\s+\w+\s*is\s+not\s+None\s*:)', "redundant_none_check",
             "Use `if x:` instead of `if x is not None:` when x is a boolean context"),
            (r'(?:==\s*True|==\s*False)', "redundant_bool_compare",
             "Use `if x:` or `if not x:` instead of comparing to True/False"),
            (r'(?:len\(.*\)\s*[>=]\s*0|len\(.*\)\s*==\s*0)', "redundant_len_check",
             "Use `if collection:` or `if not collection:` instead of len() checks"),
            (r'(?:list\(\.keys\(\)\)|list\(\.values\(\)\))', "redundant_list_wrap",
             "Iterate directly over dict keys/values without wrapping in list()"),
            (r'(?:a\s*!=\s*a)', "self_comparison", "Remove self-comparison which is always False"),
        ]

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for pattern, name, suggestion in simplification_patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    line = content[: match.start()].count("\n") + 1
                    op_id = self._oid("simplify_logic", rel, name)
                    plan.operations.append(RefactoringOperation(
                        id=op_id,
                        category="simplify_logic",
                        file=rel,
                        line=line,
                        description=f"Simplify logic: {name.replace('_', ' ')} in `{rel}`",
                        motivation=f"Simpler alternatives exist for this pattern",
                        effort_hours=0.2,
                        risk="low",
                        confidence=0.9,
                        steps=[suggestion, "Run tests to verify correctness"],
                        expected_improvement="Cleaner, more idiomatic code",
                        rollback_plan="Revert the simplified expression to its original form",
                    ))

    def _overall_risk(self, operations: list[RefactoringOperation]) -> str:
        if any(o.risk == "high" for o in operations):
            return "high"
        if any(o.risk == "medium" for o in operations):
            return "medium"
        return "low"

    def _estimate_regression(self, operations: list[RefactoringOperation]) -> float:
        if not operations:
            return 0.0
        high_risk = sum(1 for o in operations if o.risk == "high")
        medium_risk = sum(1 for o in operations if o.risk == "medium")
        total = len(operations)
        return min(0.95, (high_risk * 0.15 + medium_risk * 0.05) / max(total, 1) * total)

    def _oid(self, category: str, file: str, name: str) -> str:
        seed = f"{category}:{file}:{name}:{datetime.now(timezone.utc).isoformat()}"
        return hashlib.sha256(seed.encode()).hexdigest()[:16]

    def _try_parse(self, content: str) -> Optional[ast.AST]:
        try:
            return ast.parse(content)
        except SyntaxError:
            return None
