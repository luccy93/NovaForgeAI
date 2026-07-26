"""Repository Knowledge Graph — continuously evolving graph of repo structure, history, and relationships."""

import ast
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class NodeType(str, Enum):
    REPOSITORY = "repository"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    SERVICE = "service"
    MODULE = "module"
    FOLDER = "folder"
    FILE = "file"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    PACKAGE = "package"
    DEPENDENCY = "dependency"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    DEVELOPER = "developer"
    COMMIT = "commit"
    DEPLOYMENT = "deployment"
    TEST = "test"
    DOCUMENTATION = "documentation"
    ARCHITECTURE_COMPONENT = "architecture_component"


class RelationshipType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    USES = "uses"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    REFERENCES = "references"
    OWNS = "owns"
    REVIEWS = "reviews"
    DEPLOYS = "deploys"
    TESTS = "tests"
    DOCUMENTS = "documents"
    GENERATES = "generates"


@dataclass
class KnowledgeNode:
    id: str
    type: NodeType
    name: str
    file_path: str = ""
    language: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeEdge:
    id: str
    source_id: str
    target_id: str
    type: RelationshipType
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphSnapshot:
    timestamp: str
    node_count: int
    edge_count: int
    node_types: dict[str, int]
    relationship_types: dict[str, int]


class RepositoryKnowledgeGraph:
    """Builds and maintains a continuously evolving knowledge graph of a repository."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.repo_id = self._generate_id(str(self.repo_path))
        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KnowledgeEdge] = []
        self.history: list[GraphSnapshot] = []
        self._edge_counter = 0
        self._build_repo_node()

    def _generate_id(self, seed: str) -> str:
        return hashlib.sha256(seed.encode()).hexdigest()[:16]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_repo_node(self):
        nid = f"repo:{self.repo_id}"
        self.nodes[nid] = KnowledgeNode(
            id=nid,
            type=NodeType.REPOSITORY,
            name=self.repo_path.name,
            file_path=str(self.repo_path),
            created_at=self._now(),
            updated_at=self._now(),
            properties={
                "path": str(self.repo_path.absolute()),
                "language_stats": {},
                "file_count": 0,
                "total_lines": 0,
            },
        )

    def add_node(self, node_type: NodeType, name: str, file_path: str = "",
                 language: str = "", properties: dict = None) -> str:
        seed = f"{node_type}:{name}:{file_path}"
        nid = self._generate_id(seed)
        if nid not in self.nodes:
            self.nodes[nid] = KnowledgeNode(
                id=nid,
                type=node_type,
                name=name,
                file_path=file_path,
                language=language,
                properties=properties or {},
                created_at=self._now(),
                updated_at=self._now(),
                version=1,
            )
        else:
            self.nodes[nid].updated_at = self._now()
            self.nodes[nid].version += 1
            if properties:
                self.nodes[nid].properties.update(properties)
        return nid

    def add_edge(self, source_id: str, target_id: str, rel_type: RelationshipType,
                 weight: float = 1.0, properties: dict = None) -> str:
        self._edge_counter += 1
        seed = f"{source_id}:{target_id}:{rel_type}"
        eid = f"edge:{self._edge_counter}:{self._generate_id(seed)}"
        self.edges.append(KnowledgeEdge(
            id=eid,
            source_id=source_id,
            target_id=target_id,
            type=rel_type,
            weight=weight,
            properties=properties or {},
            created_at=self._now(),
        ))
        return eid

    def scan_repository(self) -> "RepositoryKnowledgeGraph":
        """Perform a full scan of the repository, building the knowledge graph."""
        repo_node = self.nodes.get(f"repo:{self.repo_id}")
        if not repo_node:
            self._build_repo_node()
            repo_node = self.nodes[f"repo:{self.repo_id}"]

        file_count = 0
        total_lines = 0
        lang_stats: dict[str, int] = {}

        for file_path in sorted(self.repo_path.rglob("*")):
            if not file_path.is_file() or any(
                p.startswith(".") or p in ("node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build")
                for p in file_path.parts
            ):
                continue

            rel_path = str(file_path.relative_to(self.repo_path))
            ext = file_path.suffix.lower()
            lang = self._detect_language(ext)

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.count("\n") + 1
            total_lines += lines
            file_count += 1
            lang_stats[lang] = lang_stats.get(lang, 0) + 1

            parent_parts = list(file_path.relative_to(self.repo_path).parts)
            parent_ids = [f"repo:{self.repo_id}"]

            for i, part in enumerate(parent_parts[:-1]):
                parent_path = str(self.repo_path / "/".join(parent_parts[: i + 1]))
                ntype = NodeType.MODULE if i == 0 else NodeType.FOLDER
                pid = self.add_node(ntype, part, parent_path)
                parent_ids.append(pid)

            file_nid = self.add_node(
                NodeType.FILE, rel_path, str(file_path), lang,
                {"lines": lines, "extension": ext, "size": len(content)},
            )
            for pid in parent_ids:
                self.add_edge(pid, file_nid, RelationshipType.CONTAINS)

            self._scan_file_symbols(content, ext, file_nid, rel_path)

        repo_node.properties["file_count"] = file_count
        repo_node.properties["total_lines"] = total_lines
        repo_node.properties["language_stats"] = lang_stats
        repo_node.updated_at = self._now()

        self._snapshot()
        return self

    def _detect_language(self, ext: str) -> str:
        mapping = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React", ".tsx": "React TypeScript", ".go": "Go",
            ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby",
            ".php": "PHP", ".c": "C", ".cpp": "C++", ".cs": "C#",
            ".swift": "Swift", ".scala": "Scala", ".sql": "SQL",
            ".sh": "Shell", ".yaml": "YAML", ".yml": "YAML",
            ".json": "JSON", ".xml": "XML", ".md": "Markdown",
            ".html": "HTML", ".css": "CSS", ".vue": "Vue",
        }
        return mapping.get(ext, "Unknown")

    def _scan_file_symbols(self, content: str, ext: str, file_nid: str, rel_path: str):
        if ext == ".py":
            self._scan_python_symbols(content, file_nid, rel_path)
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            self._scan_js_symbols(content, ext, file_nid, rel_path)
        elif ext == ".java":
            self._scan_java_symbols(content, file_nid, rel_path)

        imports = self._extract_imports(content, ext)
        for imp in imports:
            dep_nid = self.add_node(NodeType.DEPENDENCY, imp)
            self.add_edge(file_nid, dep_nid, RelationshipType.IMPORTS)

    def _scan_python_symbols(self, content: str, file_nid: str, rel_path: str):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                fn_nid = self.add_node(
                    NodeType.FUNCTION, node.name, rel_path, "Python",
                    {"line": node.lineno, "end_line": getattr(node, 'end_lineno', 0)},
                )
                self.add_edge(file_nid, fn_nid, RelationshipType.CONTAINS)

                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        self.add_edge(fn_nid, self._generate_id(f"function:{decorator.id}:"),
                                      RelationshipType.REFERENCES, properties={"decorator": decorator.id})

            elif isinstance(node, ast.ClassDef):
                cls_nid = self.add_node(
                    NodeType.INTERFACE, node.name, rel_path, "Python",
                    {"line": node.lineno},
                )
                self.add_edge(file_nid, cls_nid, RelationshipType.CONTAINS)

                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_nid = self.add_node(NodeType.INTERFACE, base.id)
                        self.add_edge(cls_nid, base_nid, RelationshipType.EXTENDS)

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_nid = self.add_node(
                            NodeType.METHOD, item.name, rel_path, "Python",
                            {"line": item.lineno, "class": node.name},
                        )
                        self.add_edge(cls_nid, m_nid, RelationshipType.CONTAINS)

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        call = node.value
                        if isinstance(call.func, ast.Name) and call.func.id in ("Enum", "IntEnum"):
                            self.add_node(NodeType.ENUM, target.id, rel_path, "Python")

    def _scan_js_symbols(self, content: str, ext: str, file_nid: str, rel_path: str):
        func_pattern = r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(|(\w+)\s*=\s*function)'
        for match in re.finditer(func_pattern, content):
            name = match.group(1) or match.group(2) or match.group(3)
            if name:
                fn_nid = self.add_node(NodeType.FUNCTION, name, rel_path, "JavaScript" if ext == ".js" else "TypeScript")
                self.add_edge(file_nid, fn_nid, RelationshipType.CONTAINS)

        class_pattern = r'(?:class\s+(\w+)|interface\s+(\w+)|type\s+(\w+)\s*=)'
        for match in re.finditer(class_pattern, content):
            name = match.group(1) or match.group(2) or match.group(3)
            if name:
                cls_nid = self.add_node(NodeType.INTERFACE, name, rel_path)
                self.add_edge(file_nid, cls_nid, RelationshipType.CONTAINS)

    def _scan_java_symbols(self, content: str, file_nid: str, rel_path: str):
        class_pattern = r'(?:public|private|protected)?\s*(?:abstract|final)?\s*(?:class|interface|enum)\s+(\w+)'
        for match in re.finditer(class_pattern, content):
            name = match.group(1)
            ntype = NodeType.ENUM if "enum" in match.group(0) else NodeType.INTERFACE
            nid = self.add_node(ntype, name, rel_path, "Java")
            self.add_edge(file_nid, nid, RelationshipType.CONTAINS)

        method_pattern = r'(?:public|private|protected)?\s*(?:static|final|abstract|synchronized)?\s*(?:\w+)\s+(\w+)\s*\('
        for match in re.finditer(method_pattern, content):
            name = match.group(1)
            if name and name not in ("if", "while", "for", "switch", "catch"):
                nid = self.add_node(NodeType.METHOD, name, rel_path, "Java")
                self.add_edge(file_nid, nid, RelationshipType.CONTAINS)

    def _extract_imports(self, content: str, ext: str) -> set[str]:
        imports = set()
        if ext == ".py":
            for match in re.finditer(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', content, re.MULTILINE):
                imp = match.group(1) or match.group(2)
                imports.add(imp.split(".")[0])
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            for match in re.finditer(r'(?:import|require)\s*[\s(]*["\']([^"\']+)', content):
                imp = match.group(1)
                if not imp.startswith("."):
                    imports.add(imp.split("/")[0])
        elif ext == ".java":
            for match in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
                imp = match.group(1)
                imports.add(imp.split(".")[0])
        return imports

    def query(self, node_type: Optional[NodeType] = None, name: Optional[str] = None,
              file_path: Optional[str] = None) -> list[KnowledgeNode]:
        results = list(self.nodes.values())
        if node_type:
            results = [n for n in results if n.type == node_type]
        if name:
            results = [n for n in results if name.lower() in n.name.lower()]
        if file_path:
            results = [n for n in results if file_path in n.file_path]
        return results

    def get_relationships(self, node_id: str, direction: str = "both") -> list[KnowledgeEdge]:
        if direction == "outgoing" or direction == "both":
            outgoing = [e for e in self.edges if e.source_id == node_id]
        else:
            outgoing = []
        if direction == "incoming" or direction == "both":
            incoming = [e for e in self.edges if e.target_id == node_id]
        else:
            incoming = []
        return outgoing + incoming

    def get_subgraph(self, node_id: str, depth: int = 2) -> dict[str, list]:
        visited_nodes = set()
        visited_edges = set()
        queue = [(node_id, 0)]

        while queue:
            nid, d = queue.pop(0)
            if nid in visited_nodes or d > depth:
                continue
            visited_nodes.add(nid)
            for edge in self.get_relationships(nid):
                visited_edges.add(edge.id)
                neighbor = edge.target_id if edge.source_id == nid else edge.source_id
                if neighbor not in visited_nodes:
                    queue.append((neighbor, d + 1))

        return {
            "nodes": [self.nodes[nid] for nid in visited_nodes if nid in self.nodes],
            "edges": [e for e in self.edges if e.id in visited_edges],
        }

    def to_json(self, file_path: Optional[str] = None) -> str:
        data = {
            "repo_id": self.repo_id,
            "repo_name": self.repo_path.name,
            "nodes": [n.__dict__ for n in self.nodes.values()],
            "edges": [e.__dict__ for e in self.edges],
            "history": [s.__dict__ for s in self.history],
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }
        result = json.dumps(data, indent=2, default=str)
        if file_path:
            Path(file_path).write_text(result)
        return result

    @classmethod
    def from_json(cls, file_path: str) -> "RepositoryKnowledgeGraph":
        data = json.loads(Path(file_path).read_text())
        kg = cls.__new__(cls)
        kg.repo_path = Path(data.get("repo_name", ""))
        kg.repo_id = data["repo_id"]
        kg.nodes = {n["id"]: KnowledgeNode(**n) for n in data["nodes"]}
        kg.edges = [KnowledgeEdge(**e) for e in data["edges"]]
        kg.history = [GraphSnapshot(**h) for h in data.get("history", [])]
        kg._edge_counter = len(kg.edges)
        return kg

    def get_statistics(self) -> dict[str, Any]:
        node_types = defaultdict(int)
        rel_types = defaultdict(int)
        for n in self.nodes.values():
            node_types[n.type.value] += 1
        for e in self.edges:
            rel_types[e.type.value] += 1
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": dict(node_types),
            "relationship_types": dict(rel_types),
            "history_count": len(self.history),
            "repo_path": str(self.repo_path),
        }

    def _snapshot(self):
        node_types = defaultdict(int)
        rel_types = defaultdict(int)
        for n in self.nodes.values():
            node_types[n.type.value] += 1
        for e in self.edges:
            rel_types[e.type.value] += 1
        self.history.append(GraphSnapshot(
            timestamp=self._now(),
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            node_types=dict(node_types),
            relationship_types=dict(rel_types),
        ))
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
