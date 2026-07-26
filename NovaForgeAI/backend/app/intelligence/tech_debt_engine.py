"""Technical Debt Engine — detect, quantify, prioritize, and generate remediation plans for tech debt."""

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class DebtItem:
    id: str
    category: str  # duplicate_code, dead_code, large_file, god_class, long_method, cyclic_dependency, unused_dependency, architecture_drift, layer_violation, code_smell
    file: str
    line: int = 0
    severity: str = "medium"  # critical, high, medium, low
    description: str = ""
    evidence: str = ""
    estimated_effort_hours: float = 0.0
    priority_score: float = 0.0
    suggested_fix: str = ""
    affected_symbols: list[str] = field(default_factory=list)


@dataclass
class RemedyPlan:
    debt_id: str
    action: str
    effort_hours: float
    risk: str  # low, medium, high
    steps: list[str] = field(default_factory=list)
    expected_improvement: str = ""


@dataclass
class DebtReport:
    repo_id: str
    repo_name: str
    timestamp: str
    items: list[DebtItem] = field(default_factory=list)
    total_effort_hours: float = 0.0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    debt_ratio: float = 0.0  # 0-100
    category_breakdown: dict[str, int] = field(default_factory=dict)
    remediation_plans: list[RemedyPlan] = field(default_factory=list)


class TechnicalDebtEngine:
    """Detects, quantifies, prioritizes, and generates remediation plans for technical debt."""

    SMELL_PATTERNS = {
        "empty_except": (r"except\s*:\s*pass", "low", 0.5),
        "bare_except": (r"except\s+Exception\s*:", "medium", 0.5),
        "wildcard_import": (r"import\s+\*", "medium", 0.3),
        "eval_usage": (r"\beval\s*\(", "critical", 2.0),
        "exec_usage": (r"\bexec\s*\(", "critical", 2.0),
        "shell_injection": (r"os\.system\(|subprocess\.call\(.*shell=True", "high", 1.5),
        "unsafe_deserialization": (r"pickle\.loads?\(", "high", 1.0),
        "mutable_default": (r"def\s+\w+\(.*=\s*\[\s*\]", "medium", 0.5),
        "mutable_default_dict": (r"def\s+\w+\(.*=\s*\{\s*\}", "medium", 0.5),
        "while_true": (r"while\s+True\s*:", "low", 0.5),
        "deep_nesting": (r"if\s+.*:\s*\n\s+if\s+.*:\s*\n\s+if\s+.*:\s*\n\s+if\s+", "high", 2.0),
        "magic_number": (r"(?<!\w)(?:[3-9]\d+|[1-9]\d{2,})(?!\w)(?!.*(?:def|class|import))", "low", 0.3),
        "todo_fixme": (r"#\s*(TODO|FIXME|HACK|XXX|BUG)", "low", 0.2),
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.repo_id = hashlib.sha256(str(self.repo_path).encode()).hexdigest()[:16]

    def analyze(self) -> DebtReport:
        report = DebtReport(
            repo_id=self.repo_id,
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._detect_duplicate_code(report)
        self._detect_dead_code(report)
        self._detect_large_files(report)
        self._detect_god_classes(report)
        self._detect_long_methods(report)
        self._detect_cyclic_dependencies(report)
        self._detect_code_smells(report)
        self._detect_layer_violations(report)

        report.critical_count = sum(1 for d in report.items if d.severity == "critical")
        report.high_count = sum(1 for d in report.items if d.severity == "high")
        report.medium_count = sum(1 for d in report.items if d.severity == "medium")
        report.low_count = sum(1 for d in report.items if d.severity == "low")
        report.total_effort_hours = sum(d.estimated_effort_hours for d in report.items)

        cat_counts = defaultdict(int)
        for d in report.items:
            cat_counts[d.category] += 1
        report.category_breakdown = dict(cat_counts)

        total_possible = max(100, len(report.items) * 5)
        actual_debt = sum(d.estimated_effort_hours for d in report.items if d.severity in ("critical", "high"))
        report.debt_ratio = min(100, (actual_debt / max(total_possible, 1)) * 100)

        report.remediation_plans = self._generate_remediation_plans(report)

        return report

    def _detect_duplicate_code(self, report: DebtReport):
        content_hashes: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if len(stripped) > 30 and not stripped.startswith(("#", "//", "/*", "*")):
                    h = hashlib.md5(stripped.encode()).hexdigest()
                    content_hashes[h].append((rel, i, stripped))

        seen_files: dict[str, list[str]] = defaultdict(list)
        for h, occurrences in content_hashes.items():
            if len(occurrences) >= 2:
                unique_files = set(o[0] for o in occurrences)
                if len(unique_files) >= 2:
                    for o in occurrences:
                        seen_files[o[0]].append(o[1])

        for i, (h, occurrences) in enumerate(sorted(content_hashes.items(), key=lambda x: -len(x[1]))):
            if len(occurrences) < 3:
                continue
            unique_files = set(o[0] for o in occurrences)
            if len(unique_files) >= 2:
                debt_id = f"dup-{h[:8]}"
                report.items.append(DebtItem(
                    id=debt_id,
                    category="duplicate_code",
                    file=occurrences[0][0],
                    line=occurrences[0][1],
                    severity="medium",
                    description=f"Duplicate code block found in {len(unique_files)} files ({len(occurrences)} occurrences)",
                    evidence=f"Hash {h[:8]}: {occurrences[0][2][:80]}...",
                    estimated_effort_hours=len(occurrences) * 0.5,
                    priority_score=min(10, len(occurrences)),
                    suggested_fix="Extract duplicated logic into a shared utility function or module",
                    affected_symbols=list(unique_files),
                ))
                if len(report.items) >= 20:
                    break

    def _detect_dead_code(self, report: DebtReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            defined_functions = set()
            called_functions = set()
            defined_classes = set()
            used_classes = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    defined_functions.add(node.name)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        called_functions.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        called_functions.add(node.func.attr)
                elif isinstance(node, ast.ClassDef):
                    defined_classes.add(node.name)
                elif isinstance(node, ast.Name):
                    used_classes.add(node.id)

            for fn_name in defined_functions:
                if fn_name not in called_functions and not fn_name.startswith("__"):
                    debt_id = hashlib.md5(f"dead-fn:{rel}:{fn_name}".encode()).hexdigest()[:12]
                    report.items.append(DebtItem(
                        id=debt_id,
                        category="dead_code",
                        file=rel,
                        severity="medium",
                        description=f"Potentially dead function: {fn_name}",
                        evidence=f"Defined but never called in the same file",
                        estimated_effort_hours=0.5,
                        priority_score=3,
                        suggested_fix=f"Remove function '{fn_name}' if unused across the project, or add a usage reference",
                        affected_symbols=[fn_name],
                    ))

            for cls_name in defined_classes:
                if cls_name not in used_classes and not cls_name.startswith("_"):
                    debt_id = hashlib.md5(f"dead-cls:{rel}:{cls_name}".encode()).hexdigest()[:12]
                    report.items.append(DebtItem(
                        id=debt_id,
                        category="dead_code",
                        file=rel,
                        severity="medium",
                        description=f"Potentially dead class: {cls_name}",
                        evidence=f"Defined but usage not detected in file",
                        estimated_effort_hours=1.0,
                        priority_score=3,
                        suggested_fix=f"Remove class '{cls_name}' if unused, or verify it's imported elsewhere",
                        affected_symbols=[cls_name],
                    ))

    def _detect_large_files(self, report: DebtReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
            except Exception:
                continue

            if lines > 1000:
                rel = str(f.relative_to(self.repo_path))
                debt_id = hashlib.md5(f"large:{rel}".encode()).hexdigest()[:12]
                severity = "critical" if lines > 3000 else ("high" if lines > 2000 else "medium")
                report.items.append(DebtItem(
                    id=debt_id,
                    category="large_file",
                    file=rel,
                    severity=severity,
                    description=f"Large file: {lines} lines",
                    evidence=f"File has {lines} lines of code",
                    estimated_effort_hours=lines / 100,
                    priority_score=min(10, lines / 200),
                    suggested_fix="Split file into smaller modules by functionality or concern",
                ))

    def _detect_god_classes(self, report: DebtReport):
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
                    lines = (getattr(node, 'end_lineno', 0) or 0) - node.lineno

                    if len(methods) > 15 or lines > 500:
                        debt_id = hashlib.md5(f"god:{rel}:{node.name}".encode()).hexdigest()[:12]
                        severity = "high" if len(methods) > 20 or lines > 800 else "medium"
                        report.items.append(DebtItem(
                            id=debt_id,
                            category="god_class",
                            file=rel,
                            line=node.lineno,
                            severity=severity,
                            description=f"God class: {node.name} ({len(methods)} methods, ~{lines} lines)",
                            evidence=f"Class has {len(methods)} methods spanning {lines} lines",
                            estimated_effort_hours=len(methods) * 0.5,
                            priority_score=min(10, len(methods) / 2),
                            suggested_fix=f"Split '{node.name}' into smaller focused classes using Single Responsibility Principle",
                            affected_symbols=[node.name],
                        ))

    def _detect_long_methods(self, report: DebtReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end_line = getattr(node, 'end_lineno', node.lineno) or node.lineno
                    fn_lines = end_line - node.lineno

                    if fn_lines > 50:
                        debt_id = hashlib.md5(f"long-fn:{rel}:{node.name}".encode()).hexdigest()[:12]
                        severity = "high" if fn_lines > 100 else ("medium" if fn_lines > 75 else "low")
                        report.items.append(DebtItem(
                            id=debt_id,
                            category="long_method",
                            file=rel,
                            line=node.lineno,
                            severity=severity,
                            description=f"Long method: {node.name} ({fn_lines} lines)",
                            evidence=f"Method spans {fn_lines} lines",
                            estimated_effort_hours=fn_lines / 50,
                            priority_score=min(8, fn_lines / 20),
                            suggested_fix=f"Extract method '{node.name}' into smaller helper functions",
                            affected_symbols=[node.name],
                        ))

    def _detect_cyclic_dependencies(self, report: DebtReport):
        import_graph: dict[str, set[str]] = defaultdict(set)

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for match in re.finditer(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', content, re.MULTILINE):
                imp = match.group(1) or match.group(2)
                imp_module = imp.split(".")[0]
                if imp_module != rel.replace(".py", "").replace("/", "."):
                    import_graph[rel].add(imp_module)

        def detect_cycles(graph):
            cycles = []
            visited = set()
            rec_stack = set()
            path = []

            def dfs(node):
                if node in rec_stack:
                    cycle_start = path.index(node)
                    cycles.append(path[cycle_start:] + [node])
                    return
                if node in visited:
                    return
                visited.add(node)
                rec_stack.add(node)
                path.append(node)
                for neighbor in graph.get(node, set()):
                    neighbor_file = next((k for k in graph if neighbor in k.replace(".py", "").replace("/", ".") or k.startswith(neighbor)), None)
                    if neighbor_file:
                        dfs(neighbor_file)
                path.pop()
                rec_stack.discard(node)

            for node in graph:
                dfs(node)
            return cycles

        cycles = detect_cycles(import_graph)
        for cycle in cycles[:10]:
            cycle_str = " -> ".join(cycle)
            debt_id = hashlib.md5(f"cycle:{cycle_str}".encode()).hexdigest()[:12]
            report.items.append(DebtItem(
                id=debt_id,
                category="cyclic_dependency",
                file=cycle[0],
                severity="high",
                description=f"Cyclic dependency detected ({len(cycle)} modules)",
                evidence=f"Dependency cycle: {cycle_str}",
                estimated_effort_hours=len(cycle) * 2.0,
                priority_score=min(10, len(cycle) * 2),
                suggested_fix="Break the cycle by extracting shared dependencies or using dependency inversion",
                affected_symbols=cycle,
            ))

    def _detect_code_smells(self, report: DebtItem):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for smell, (pattern, severity, effort) in self.SMELL_PATTERNS.items():
                if smell == "magic_number":
                    for match in re.finditer(pattern, content, re.MULTILINE):
                        line_num = content[: match.start()].count("\n") + 1
                        debt_id = hashlib.md5(f"smell:{rel}:{line_num}:{smell}".encode()).hexdigest()[:12]
                        report.items.append(DebtItem(
                            id=debt_id,
                            category="code_smell",
                            file=rel,
                            line=line_num,
                            severity=severity,
                            description=f"Code smell: {smell.replace('_', ' ')}",
                            evidence=f"Pattern: {smell} at line {line_num}",
                            estimated_effort_hours=effort,
                            priority_score=1.0,
                            suggested_fix=self._suggested_fix_for(smell),
                        ))
                else:
                    for match in re.finditer(pattern, content, re.MULTILINE):
                        line_num = content[: match.start()].count("\n") + 1
                        debt_id = hashlib.md5(f"smell:{rel}:{line_num}:{smell}".encode()).hexdigest()[:12]
                        report.items.append(DebtItem(
                            id=debt_id,
                            category="code_smell",
                            file=rel,
                            line=line_num,
                            severity=severity,
                            description=f"Code smell: {smell.replace('_', ' ')}",
                            evidence=f"Pattern: {smell} at line {line_num}",
                            estimated_effort_hours=effort,
                            priority_score=2.0 if severity == "high" else (1.0 if severity == "medium" else 0.5),
                            suggested_fix=self._suggested_fix_for(smell),
                        ))

    def _detect_layer_violations(self, report: DebtReport):
        layer_patterns = {
            "presentation": ["view", "controller", "routes", "web", "api", "ui"],
            "application": ["service", "use_case", "interactor", "command", "query"],
            "domain": ["model", "entity", "domain", "value_object", "aggregate"],
            "infrastructure": ["repository", "database", "persistence", "cache", "queue", "client"],
        }

        layer_files: dict[str, list[str]] = defaultdict(list)
        for f in self.repo_path.rglob("*.py"):
            rel = str(f.relative_to(self.repo_path))
            for layer, patterns in layer_patterns.items():
                if any(p in rel.lower() for p in patterns):
                    layer_files[layer].append(rel)

        violations = []
        presentation_imports_domain = 0
        for pf in layer_files.get("presentation", []):
            try:
                content = (self.repo_path / pf).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for df in layer_files.get("domain", []):
                domain_module = df.replace(".py", "").replace("/", ".")
                imp_pattern = rf"(?:from\s+{domain_module}|import\s+{domain_module})"
                if re.search(imp_pattern, content):
                    presentation_imports_domain += 1

        if presentation_imports_domain > 0:
            violations.append(("Layer violation: Presentation layer imports Domain layer", "high", 2.0))

        infra_imports_presentation = 0
        for inf in layer_files.get("infrastructure", []):
            try:
                content = (self.repo_path / inf).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pf in layer_files.get("presentation", []):
                pres_module = pf.replace(".py", "").replace("/", ".")
                imp_pattern = rf"(?:from\s+{pres_module}|import\s+{pres_module})"
                if re.search(imp_pattern, content):
                    infra_imports_presentation += 1

        if infra_imports_presentation > 0:
            violations.append(("Layer violation: Infrastructure layer imports Presentation layer", "high", 2.0))

        for violation in violations:
            desc, severity, effort = violation
            debt_id = hashlib.md5(f"layer:{desc}".encode()).hexdigest()[:12]
            report.items.append(DebtItem(
                id=debt_id,
                category="layer_violation",
                file="(multiple files)",
                severity=severity,
                description=desc,
                evidence=desc,
                estimated_effort_hours=effort,
                priority_score=7.0,
                suggested_fix="Apply Dependency Inversion Principle; inject dependencies through interfaces",
            ))

    def _suggested_fix_for(self, smell: str) -> str:
        fixes = {
            "empty_except": "Add exception handling logic or catch specific exceptions",
            "bare_except": "Catch specific exception types instead of broad Exception",
            "wildcard_import": "Import specific names: `from module import SpecificName`",
            "eval_usage": "Replace with ast.literal_eval or proper parsing logic",
            "exec_usage": "Replace with function calls or method dispatch",
            "shell_injection": "Use subprocess with list arguments, avoid shell=True",
            "unsafe_deserialization": "Use json or safer serialization instead of pickle",
            "mutable_default": "Use None as default and initialize inside function: `def fn(x=None): if x is None: x = []`",
            "mutable_default_dict": "Use None as default and initialize inside function",
            "while_true": "Add explicit termination condition or timeout mechanism",
            "deep_nesting": "Flatten nesting with early returns, guard clauses, or extraction",
            "magic_number": "Replace magic numbers with named constants",
            "todo_fixme": "Address TODO/FIXME items in a dedicated refactoring session",
        }
        return fixes.get(smell, "Review and refactor this code")

    def _generate_remediation_plans(self, report: DebtReport) -> list[RemedyPlan]:
        plans = []
        sorted_items = sorted(report.items, key=lambda x: x.priority_score, reverse=True)

        for item in sorted_items[:20]:
            if item.category == "duplicate_code":
                steps = [
                    f"Identify all locations of duplicate code in {', '.join(item.affected_symbols[:5])}",
                    "Extract the common logic into a shared utility function",
                    "Replace all duplicate instances with calls to the new function",
                    "Add unit tests for the extracted function",
                    "Run existing tests to verify no regression",
                ]
            elif item.category == "god_class":
                steps = [
                    f"Analyze responsibilities of class {item.affected_symbols[0] if item.affected_symbols else item.file}",
                    "Identify cohesive groups of methods that can be extracted",
                    "Create new focused classes for each responsibility group",
                    "Update references to use the new classes",
                    "Verify behavior with existing tests",
                ]
            elif item.category == "long_method":
                steps = [
                    f"Review method at {item.file}:{item.line}",
                    "Identify logical blocks that can be extracted as helper functions",
                    "Extract each block with clear naming",
                    "Ensure extracted functions are testable",
                    "Run tests to verify correctness",
                ]
            elif item.category == "cyclic_dependency":
                steps = [
                    f"Analyze dependency cycle involving {', '.join(item.affected_symbols[:5])}",
                    "Identify the dependency inversion point",
                    "Extract an interface or shared module that both can depend on",
                    "Update import statements",
                    "Verify no circular imports remain",
                ]
            elif item.category == "layer_violation":
                steps = [
                    f"Identify the layer boundary violation",
                    "Create an interface in the appropriate layer",
                    "Inject the dependency rather than importing directly",
                    "Update all affected imports",
                    "Verify architecture compliance",
                ]
            elif item.category == "code_smell":
                steps = [
                    f"Address {item.description} at {item.file}:{item.line}",
                    item.suggested_fix,
                    "Review for similar patterns elsewhere",
                    "Run tests to verify fix",
                    "Update any affected documentation",
                ]
            else:
                steps = [
                    f"Review {item.description} at {item.file}",
                    item.suggested_fix,
                    "Run tests to verify no regression",
                ]

            plans.append(RemedyPlan(
                debt_id=item.id,
                action=item.suggested_fix,
                effort_hours=item.estimated_effort_hours,
                risk="low" if item.severity == "low" else ("medium" if item.severity == "medium" else "high"),
                steps=steps,
                expected_improvement=f"Resolve {item.category}: {item.description}",
            ))

        return plans
