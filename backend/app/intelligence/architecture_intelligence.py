"""Architecture Intelligence — automatic diagram generation, microservices/modules/layers detection, data flow."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class ArchitectureNode:
    id: str
    name: str
    type: str  # service, module, layer, component, database, api, queue
    language: str = ""
    description: str = ""
    children: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ArchitectureEdge:
    source: str
    target: str
    type: str  # calls, depends_on, contains, data_flow, api_call, message
    weight: int = 1
    metadata: dict = field(default_factory=dict)


@dataclass
class ArchitectureModel:
    repo_id: str
    repo_name: str
    nodes: list[ArchitectureNode] = field(default_factory=list)
    edges: list[ArchitectureEdge] = field(default_factory=list)
    detected_patterns: list[str] = field(default_factory=list)
    dependency_cycles: list[list[str]] = field(default_factory=list)
    timestamp: str = ""


class ArchitectureIntelligence:
    """Detects architecture patterns, generates diagrams, tracks evolution."""

    _history: dict[str, list[ArchitectureModel]] = defaultdict(list)

    # Patterns to detect architectural styles
    SERVICE_PATTERNS = {
        "microservice": [
            r"class\s+\w+Service",
            r"@app\.route|@router\.(get|post|put|delete|patch)",
            r"def\s+\w+_handler",
        ],
        "repository": [
            r"class\s+\w+Repository",
            r"def\s+(get|find|save|delete|update)_\w+",
        ],
        "controller": [
            r"class\s+\w+Controller",
            r"class\s+\w+Resource",
            r"class\s+\w+ViewSet",
        ],
        "middleware": [
            r"class\s+\w+Middleware",
            r"def\s+(\w+_)?middleware",
            r"@app\.middleware",
        ],
        "event_driven": [
            r"class\s+\w+Event",
            r"async\s+def\s+handle_\w+",
            r"def\s+publish_\w+",
            r"def\s+subscribe_\w+",
        ],
        "plugin": [
            r"class\s+\w+Plugin",
            r"def\s+(load|register|initialize)_plugin",
        ],
    }

    LAYER_PATTERNS = {
        "presentation": [r"(controller|view|ui|web|api|route)", r"\.html$", r"\.vue$", r"\.jsx$", r"\.tsx$"],
        "application": [r"(service|use_case|interactor|command|query)", r"application"],
        "domain": [r"(model|entity|domain|value_object|aggregate)", r"domain"],
        "infrastructure": [r"(repository|database|persistence|cache|queue|client)", r"infrastructure"],
        "cross_cutting": [r"(logging|auth|security|config|middleware)", r"common|shared|core"],
    }

    @staticmethod
    def analyze(repo_path: str) -> ArchitectureModel:
        path = Path(repo_path)
        model = ArchitectureModel(
            repo_id=str(hash(str(path))),
            repo_name=path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        import_map: dict[str, set[str]] = defaultdict(set)
        file_map: dict[str, str] = {}
        service_patterns_found: set[str] = set()
        layer_files: dict[str, list[str]] = defaultdict(list)

        for file_path in sorted(path.rglob("*")):
            if not file_path.is_file() or any(
                p.startswith(".") or p in ("node_modules", "__pycache__", ".git", "venv", ".venv")
                for p in file_path.parts
            ):
                continue

            rel = str(file_path.relative_to(path))
            ext = file_path.suffix.lower()

            if ext not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php"):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            file_map[rel] = content

            # Detect imports/dependencies
            import_map[rel] = ArchitectureIntelligence._extract_imports(content, ext)

            # Detect architectural patterns
            for pattern_name, patterns in ArchitectureIntelligence.SERVICE_PATTERNS.items():
                for p in patterns:
                    if re.search(p, content, re.IGNORECASE):
                        service_patterns_found.add(pattern_name)
                        break

            # Classify into layers
            for layer, patterns in ArchitectureIntelligence.LAYER_PATTERNS.items():
                for p in patterns:
                    if re.search(p, rel, re.IGNORECASE) or re.search(p, content[:500], re.IGNORECASE):
                        layer_files[layer].append(rel)
                        break

        # Build nodes
        node_id_map: dict[str, str] = {}

        if service_patterns_found:
            for svc in service_patterns_found:
                nid = f"svc-{svc}"
                node_id_map[svc] = nid
                model.nodes.append(ArchitectureNode(
                    id=nid, name=svc.replace("_", " ").title(),
                    type="service", description=f"{svc} architecture pattern",
                ))

        for layer, files in layer_files.items():
            if files:
                nid = f"layer-{layer}"
                model.nodes.append(ArchitectureNode(
                    id=nid, name=layer.title(),
                    type="layer", description=f"{len(files)} files in {layer} layer",
                    children=files[:10],
                ))

        # Detect module structure
        top_dirs = sorted(set(
            p.split("/")[0] for p in file_map.keys() if "/" in p
        ))
        for td in top_dirs[:15]:
            nid = f"mod-{td}"
            node_id_map[td] = nid
            model.nodes.append(ArchitectureNode(
                id=nid, name=td, type="module",
                description=f"Module: {td}",
            ))

        # Build edges from imports
        for source, targets in import_map.items():
            source_mod = source.split("/")[0]
            source_id = node_id_map.get(source_mod)
            if not source_id:
                continue
            for target in targets:
                target_mod = target.split(".")[0] if "." in target else target
                if target_mod in node_id_map:
                    target_id = node_id_map[target_mod]
                    if source_id != target_id:
                        model.edges.append(ArchitectureEdge(
                            source=source_id, target=target_id,
                            type="depends_on",
                        ))

        # Detect dependency cycles using DFS
        model.dependency_cycles = ArchitectureIntelligence._detect_cycles(node_id_map, model.edges)

        detected = sorted(service_patterns_found)
        framework = ArchitectureIntelligence._detect_framework(path)
        if framework:
            detected.append(f"framework:{framework}")
        model.detected_patterns = detected

        ArchitectureIntelligence._history[model.repo_id].append(model)
        if len(ArchitectureIntelligence._history[model.repo_id]) > 100:
            ArchitectureIntelligence._history[model.repo_id] = (
                ArchitectureIntelligence._history[model.repo_id][-100:]
            )

        return model

    @staticmethod
    def _extract_imports(content: str, ext: str) -> set[str]:
        imports = set()
        if ext == ".py":
            for match in re.finditer(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', content, re.MULTILINE):
                imp = match.group(1) or match.group(2)
                imports.add(imp.split(".")[0] if "." in imp else imp)
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            for match in re.finditer(r'(?:import|require)\s*[\s(]*["\']([^"\']+)', content):
                imp = match.group(1)
                if not imp.startswith("."):
                    imports.add(imp.split("/")[0])
        return imports

    @staticmethod
    def _detect_framework(repo_path: Path) -> Optional[str]:
        if (repo_path / "requirements.txt").exists():
            try:
                reqs = (repo_path / "requirements.txt").read_text().lower()
                for fw in ["fastapi", "django", "flask", "aiohttp", "tornado"]:
                    if fw in reqs:
                        return fw
            except Exception:
                pass
        if (repo_path / "package.json").exists():
            try:
                pkg = json.loads((repo_path / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                for fw in ["next", "nuxt", "express", "react", "vue", "angular", "svelte"]:
                    if fw in deps:
                        return fw
            except Exception:
                pass
        return None

    @staticmethod
    def _detect_cycles(nodes: dict[str, str], edges: list[ArchitectureEdge]) -> list[list[str]]:
        graph = defaultdict(set)
        for e in edges:
            graph[e.source].add(e.target)

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
                if neighbor in nodes.values():
                    dfs(neighbor)
            path.pop()
            rec_stack.discard(node)

        for nid in set(nodes.values()):
            dfs(nid)

        return cycles

    @staticmethod
    def generate_mermaid_diagram(model: ArchitectureModel) -> str:
        lines = ["graph TD"]
        for node in model.nodes:
            safe_name = node.name.replace(" ", "_").replace("-", "_")
            lines.append(f"    {node.id}[{node.name}]")

        for edge in model.edges[:50]:
            lines.append(f"    {edge.source} -->|{edge.type}| {edge.target}")

        if model.dependency_cycles:
            lines.append("")
            lines.append("%% Dependency Cycles Detected:")
            for i, cycle in enumerate(model.dependency_cycles):
                cycle_str = " -> ".join(cycle)
                lines.append(f"    %% Cycle {i+1}: {cycle_str}")

        return "\n".join(lines)

    @staticmethod
    def generate_d2_diagram(model: ArchitectureModel) -> str:
        lines = [f"# Architecture: {model.repo_name}", ""]
        for node in model.nodes:
            lines.append(f"{node.id}: {node.name}")

        lines.append("")
        for edge in model.edges[:50]:
            lines.append(f"{edge.source} -> {edge.target}: {edge.type}")
        return "\n".join(lines)

    @staticmethod
    def get_evolution(repo_id: str) -> list[ArchitectureModel]:
        return ArchitectureIntelligence._history.get(repo_id, [])


