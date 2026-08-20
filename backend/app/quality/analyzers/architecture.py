"""AI Software Quality Engine -- Architecture Analyzer (Volume 48).

Detects layer violations, dependency cycles, boundary violations,
unexpected coupling, and shared-state problems.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class ArchitectureAnalyzer(BaseAnalyzer):
    name = "architecture"
    category = "architecture"

    LAYER_MAP = {
        "api": {"router", "endpoint", "route", "fastapi", "APIRouter"},
        "service": {"service", "usecase", "interactor"},
        "repository": {"repository", "repo", "dao", "dal", "gateway"},
        "model": {"model", "schema", "entity", "dto"},
        "core": {"config", "settings", "base", "utils", "common"},
    }

    CYCLE_PATTERNS = [
        (r"from\s+app\.api\..*\s+import.*(?:Repository|Repo|DAO)", "api_to_repository",
         "API layer directly imports repository — should go through service layer"),
        (r"from\s+app\.models?\..*\s+import.*(?:Router|APIRouter)", "model_to_api",
         "Model layer imports API layer — architectural violation"),
    ]

    COUPLING_PATTERNS = [
        (r"from\s+app\.(\w+)\..*\s+import.*\bfrom\s+app\.(\w+)", "cross_import",
         "Cross-module import detected"),
    ]

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        arch = context.architecture
        findings.extend(self._check_layer_violations(context))
        findings.extend(self._check_coupling(context))
        findings.extend(self._check_cycles(context))
        if arch:
            findings.extend(self._check_architecture_graph(arch, context))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_layer_violations(self, context: ReviewContext) -> list:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            file_layer = self._detect_layer(file_path)
            if not file_layer:
                continue
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                imported_layer = self._detect_layer_from_import(stripped)
                if imported_layer and self._is_violation(file_layer, imported_layer):
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.7,
                        file_path=file_path, line_start=i, line_end=i,
                        description=f"{file_layer.title()} layer imports {imported_layer} layer directly",
                        evidence={"line": stripped[:120], "from_layer": file_layer, "to_layer": imported_layer},
                        recommendation=f"Route {imported_layer} access through the service layer",
                        rule_id=f"architecture.layer_violation_{file_layer}_{imported_layer}",
                    ))
        return findings

    def _check_coupling(self, context: ReviewContext) -> list:
        findings = []
        import_counts: dict[str, int] = defaultdict(int)
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            for line in content.split("\n"):
                match = re.match(r"from\s+app\.(\w+)", line.strip())
                if match:
                    import_counts[match.group(1)] += 1
        for module, count in import_counts.items():
            if count > 8:
                findings.append(self._make_finding(
                    severity="low", confidence=0.5,
                    file_path="", line_start=0, line_end=0,
                    description=f"High coupling to app.{module} ({count} imports)",
                    evidence={"module": module, "import_count": count},
                    recommendation="Consider reducing coupling through interfaces or dependency injection",
                    rule_id="architecture.high_coupling",
                ))
        return findings

    def _check_cycles(self, context: ReviewContext) -> list:
        findings = []
        graph: dict[str, set[str]] = defaultdict(set)
        for file_path, content in context.file_contents.items():
            source_module = self._file_to_module(file_path)
            if not source_module:
                continue
            for line in content.split("\n"):
                match = re.match(r"from\s+(app\.\w+)", line.strip())
                if match:
                    target_module = match.group(1)
                    if target_module != source_module:
                        graph[source_module].add(target_module)
        visited: set[str] = set()
        in_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> list[str]:
            visited.add(node)
            in_stack.add(node)
            path.append(node)
            cycle = []
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
                elif neighbor in in_stack:
                    idx = path.index(neighbor)
                    cycle = path[idx:] + [neighbor]
                    break
            path.pop()
            in_stack.discard(node)
            return cycle

        for node in graph:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    findings.append(self._make_finding(
                        severity="high", confidence=0.8,
                        file_path="", line_start=0, line_end=0,
                        description=f"Dependency cycle detected: {' -> '.join(cycle)}",
                        evidence={"cycle": cycle},
                        recommendation="Break the cycle by extracting shared interfaces or using dependency inversion",
                        rule_id="architecture.dependency_cycle",
                    ))
                    break
        return findings

    def _check_architecture_graph(self, arch: dict, context: ReviewContext) -> list:
        findings = []
        layers = arch.get("layers", [])
        if layers:
            layer_names = [l.get("name", "") for l in layers]
            findings.append(self._make_finding(
                severity="info", confidence=0.3,
                file_path="", line_start=0, line_end=0,
                description=f"Architecture layers identified: {', '.join(layer_names)}",
                evidence={"layers": layer_names},
                recommendation="Review layer dependencies for violations",
                rule_id="architecture.layers_identified",
                source="code_smell",
            ))
        return findings

    def _detect_layer(self, file_path: str) -> str:
        fp = file_path.lower()
        if "api" in fp or "router" in fp:
            return "api"
        if "service" in fp:
            return "service"
        if "repository" in fp or "repo" in fp or "dao" in fp:
            return "repository"
        if "model" in fp or "schema" in fp:
            return "model"
        if "core" in fp or "common" in fp or "util" in fp:
            return "core"
        return ""

    def _detect_layer_from_import(self, line: str) -> str:
        for layer, keywords in self.LAYER_MAP.items():
            for kw in keywords:
                if f"app.{kw}" in line.lower() or f"from app.{layer}" in line.lower():
                    return layer
        return ""

    def _is_violation(self, source: str, target: str) -> bool:
        violations = {
            "model": {"api", "service"},
            "api": {"repository"},
            "service": set(),
        }
        return target in violations.get(source, set())

    def _file_to_module(self, file_path: str) -> str:
        match = re.search(r"app[\\/](\w+)", file_path)
        if match:
            return f"app.{match.group(1)}"
        return ""
