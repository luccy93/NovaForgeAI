"""Data Lineage - tracks source to insight for every analytical artifact."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class LineageKinds:
    SOURCE = "source"
    INGESTION = "ingestion"
    TRANSFORMATION = "transform"
    AGGREGATION = "aggregation"
    STORAGE = "storage"
    QUERY = "query"
    REPORT = "report"
    AI_INSIGHT = "ai_insight"


@dataclass
class LineageNode:
    node_id: str
    kind: str
    name: str
    inputs: list[str] = field(default_factory=list)
    attrs: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.node_id:
            self.node_id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class LineageGraph:
    """Directed graph of data provenance; every node records its inputs."""

    def __init__(self):
        self.nodes: dict[str, LineageNode] = {}

    def add(self, kind: str, name: str, inputs: list[str] = None, **attrs) -> LineageNode:
        node = LineageNode(node_id=uuid.uuid4().hex[:12], kind=kind, name=name,
                           inputs=inputs or [], attrs=attrs)
        self.nodes[node.node_id] = node
        return node

    def kind(self, id: str) -> str|None:
        node = self.nodes.get(id)
        return node.kind if node else None

    def trace_back(self, node_id: str) -> list[LineageNode]:
        """Walks inputs recursively to reveal the full lineage chain."""
        seen: set[str] = set()
        chain: list[LineageNode] = []
        stack = [node_id] if node_id else []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            node = self.nodes.get(current)
            if not node:
                continue
            chain.append(node)
            stack.extend(node.inputs)
        return list(reversed(chain))

    def downstream(self, node_id: str) -> list[LineageNode]:
        """Nodes that depend (directly or transitively) on node_id."""
        result = []
        for node in self.nodes.values():
            if node_id in (node.inputs or []):
                result.append(node)
                result.extend(self.downstream(node.node_id))
        return result

    def render_chain(self, node_id: str) -> str:
        chain = self.trace_back(node_id)
        return " -> ".join(f"{n.kind}:{n.name}" for n in chain) if chain else "no lineage"

    def graph(self) -> dict:
        return {"nodes": [{"id": n.node_id, "kind": n.kind, "name": n.name,
                           "inputs": n.inputs, "attrs": n.attrs}
                          for n in self.nodes.values()]}