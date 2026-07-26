"""Knowledge Graph module for NovaForge Data Platform & Knowledge Fabric."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class GraphEntityType(Enum):
    ORGANIZATION = "organization"
    TEAM = "team"
    REPOSITORY = "repository"
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"
    SERVICE = "service"
    API = "api"
    DATABASE = "database"
    DEVELOPER = "developer"
    AGENT = "agent"
    PROMPT = "prompt"
    MODEL = "model"
    REPORT = "report"
    DOCUMENT = "document"
    DATASET = "dataset"
    PIPELINE = "pipeline"
    DASHBOARD = "dashboard"
    WORKSPACE = "workspace"
    COMMIT = "commit"
    PR = "pr"
    ISSUE = "issue"
    SECURITY_FINDING = "security_finding"
    DEPLOYMENT = "deployment"
    TEST = "test"
    CONFIGURATION = "configuration"
    INTEGRATION = "integration"


class GraphRelationType(Enum):
    OWNS = "owns"
    DEPENDS_ON = "depends_on"
    COMMUNICATES_WITH = "communicates_with"
    USES = "uses"
    CONTAINS = "contains"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    COMPOSES = "composes"
    DERIVES_FROM = "derives_from"
    GENERATES = "generates"
    CONSUMES = "consumes"
    PRODUCES = "produces"
    DEPLOYS = "deploys"
    TESTS = "tests"
    DOCUMENTS = "documents"
    MONITORS = "monitors"
    APPROVES = "approves"
    REVIEWS = "reviews"
    ASSIGNED_TO = "assigned_to"
    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"
    RELATES_TO = "relates_to"


class GraphTraversal(Enum):
    BFS = "bfs"
    DFS = "dfs"
    SHORTEST_PATH = "shortest_path"
    ALL_PATHS = "all_paths"
    COMMUNITY = "community"


class GraphAggregation(Enum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    DISTINCT = "distinct"


@dataclass
class GraphNode:
    id: str
    org_id: str
    entity_type: GraphEntityType
    name: str
    qualified_name: str = ""
    description: str = ""
    properties: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    importance: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        data = data.copy()
        data["entity_type"] = GraphEntityType(data.get("entity_type", "repository"))
        return cls(**data)


@dataclass
class GraphEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: GraphRelationType
    properties: dict = field(default_factory=dict)
    weight: float = 1.0
    bidirectional: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relation_type"] = self.relation_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        data = data.copy()
        data["relation_type"] = GraphRelationType(data.get("relation_type", "related_to"))
        return cls(**data)


@dataclass
class GraphPath:
    id: str
    source_id: str
    target_id: str
    path: list = field(default_factory=list)
    length: int = 0
    total_weight: float = 0.0
    found: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphPath":
        return cls(**data)


@dataclass
class GraphCommunity:
    id: str
    org_id: str
    name: str = ""
    description: str = ""
    node_ids: list = field(default_factory=list)
    edge_count: int = 0
    density: float = 0.0
    centrality_scores: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphCommunity":
        return cls(**data)


@dataclass
class GraphAnalytics:
    id: str
    org_id: str
    total_nodes: int = 0
    total_edges: int = 0
    by_entity_type: dict = field(default_factory=dict)
    by_relation_type: dict = field(default_factory=dict)
    avg_degree: float = 0.0
    density: float = 0.0
    connected_components: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphAnalytics":
        return cls(**data)


class KnowledgeGraph:
    def __init__(self, storage_dir: str = "knowledge_graph_data"):
        self.storage_dir = storage_dir
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._paths: dict[str, GraphPath] = {}
        self._communities: dict[str, GraphCommunity] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _nodes_path(self) -> str: return os.path.join(self.storage_dir, "nodes.json")
    def _edges_path(self) -> str: return os.path.join(self.storage_dir, "edges.json")
    def _paths_path(self) -> str: return os.path.join(self.storage_dir, "paths.json")
    def _communities_path(self) -> str: return os.path.join(self.storage_dir, "communities.json")

    def _save(self) -> None:
        try:
            with open(self._nodes_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._nodes.items()}, f, indent=2, default=str)
            with open(self._edges_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._edges.items()}, f, indent=2, default=str)
            with open(self._paths_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._paths.items()}, f, indent=2, default=str)
            with open(self._communities_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._communities.items()}, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save knowledge graph data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            for path, store, cls in [
                (self._nodes_path(), self._nodes, GraphNode),
                (self._edges_path(), self._edges, GraphEdge),
                (self._paths_path(), self._paths, GraphPath),
                (self._communities_path(), self._communities, GraphCommunity),
            ]:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try:
                            store[k] = cls.from_dict(v)
                        except Exception as e:
                            logger.warning("Skipping malformed entry %s: %s", k, e)
        except Exception as e:
            logger.error("Failed to load knowledge graph data: %s", e, exc_info=True)

    def add_node(self, node: GraphNode) -> GraphNode:
        self._telemetry["add_node_calls"] += 1
        self._nodes[node.id] = node
        self._save()
        return node

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, updates: dict) -> Optional[GraphNode]:
        self._telemetry["update_node_calls"] += 1
        node = self._nodes.get(node_id)
        if not node:
            return None
        for key, value in updates.items():
            if hasattr(node, key) and key not in ("id", "created_at"):
                if key == "entity_type":
                    setattr(node, key, GraphEntityType(value) if isinstance(value, str) else value)
                else:
                    setattr(node, key, value)
        node.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return node

    def delete_node(self, node_id: str) -> bool:
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._edges = {k: v for k, v in self._edges.items() if v.source_id != node_id and v.target_id != node_id}
            self._save()
            return True
        return False

    def search_nodes(self, query: str, entity_type: Optional[GraphEntityType] = None) -> list[GraphNode]:
        q = query.lower()
        results = []
        for node in self._nodes.values():
            if entity_type and node.entity_type != entity_type:
                continue
            if q in node.name.lower() or q in node.qualified_name.lower() or q in node.description.lower():
                results.append(node)
        return results

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        self._telemetry["add_edge_calls"] += 1
        if edge.source_id not in self._nodes or edge.target_id not in self._nodes:
            logger.warning("Cannot add edge: source or target node not found")
            return edge
        self._edges[edge.id] = edge
        self._save()
        return edge

    def get_neighbors(self, node_id: str, relation_type: Optional[GraphRelationType] = None, depth: int = 1) -> list[dict]:
        visited = {node_id}
        current = [node_id]
        results = []
        for d in range(depth):
            neighbors = []
            for nid in current:
                for edge in self._edges.values():
                    if relation_type and edge.relation_type != relation_type:
                        continue
                    other = None
                    if edge.source_id == nid and edge.target_id not in visited:
                        other = edge.target_id
                    elif edge.bidirectional and edge.target_id == nid and edge.source_id not in visited:
                        other = edge.source_id
                    if other:
                        visited.add(other)
                        node = self._nodes.get(other)
                        if node:
                            results.append({"node": node, "edge": edge, "depth": d + 1})
                        neighbors.append(other)
            current = neighbors
        return results

    def find_shortest_path(self, source_id: str, target_id: str) -> GraphPath:
        if source_id not in self._nodes or target_id not in self._nodes:
            return GraphPath(id=str(uuid.uuid4()), source_id=source_id, target_id=target_id, found=False)
        q = deque([(source_id, [source_id])])
        visited = {source_id}
        while q:
            current, path = q.popleft()
            for edge in self._edges.values():
                if edge.source_id == current:
                    neighbor = edge.target_id
                elif edge.bidirectional and edge.target_id == current:
                    neighbor = edge.source_id
                else:
                    continue
                if neighbor == target_id:
                    full_path = path + [neighbor]
                    path_nodes = []
                    total_weight = 0.0
                    for i in range(len(full_path) - 1):
                        for e in self._edges.values():
                            if (e.source_id == full_path[i] and e.target_id == full_path[i+1]) or (e.bidirectional and e.target_id == full_path[i] and e.source_id == full_path[i+1]):
                                path_nodes.append({"from": full_path[i], "to": full_path[i+1], "edge": e.to_dict()})
                                total_weight += e.weight
                                break
                    gp = GraphPath(id=str(uuid.uuid4()), source_id=source_id, target_id=target_id, path=path_nodes, length=len(full_path) - 1, total_weight=total_weight, found=True)
                    self._paths[gp.id] = gp
                    self._save()
                    return gp
                if neighbor not in visited:
                    visited.add(neighbor)
                    q.append((neighbor, path + [neighbor]))
        return GraphPath(id=str(uuid.uuid4()), source_id=source_id, target_id=target_id, found=False)

    def find_all_paths(self, source_id: str, target_id: str, max_depth: int = 5) -> list[GraphPath]:
        paths = []
        def dfs(current, target, visited, path_edges, depth):
            if depth > max_depth:
                return
            if current == target and path_edges:
                path_nodes = []
                tw = 0.0
                for e in path_edges:
                    path_nodes.append({"from": e.source_id, "to": e.target_id, "edge": e.to_dict()})
                    tw += e.weight
                paths.append(GraphPath(id=str(uuid.uuid4()), source_id=source_id, target_id=target_id, path=path_nodes, length=len(path_edges), total_weight=tw, found=True))
                return
            for edge in self._edges.values():
                next_node = None
                if edge.source_id == current and edge.target_id not in visited:
                    next_node = edge.target_id
                elif edge.bidirectional and edge.target_id == current and edge.source_id not in visited:
                    next_node = edge.source_id
                if next_node:
                    visited.add(next_node)
                    dfs(next_node, target, visited, path_edges + [edge], depth + 1)
                    visited.remove(next_node)
        dfs(source_id, target_id, {source_id}, [], 0)
        return paths

    def detect_communities(self) -> list[GraphCommunity]:
        all_node_ids = set(self._nodes.keys())
        communities = []
        visited = set()
        for nid in all_node_ids:
            if nid in visited:
                continue
            component = set()
            q = deque([nid])
            while q:
                current = q.popleft()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                for edge in self._edges.values():
                    if edge.source_id == current and edge.target_id not in visited:
                        q.append(edge.target_id)
                    elif edge.bidirectional and edge.target_id == current and edge.source_id not in visited:
                        q.append(edge.source_id)
            if component:
                edge_count = sum(1 for e in self._edges.values() if e.source_id in component and e.target_id in component)
                n = len(component)
                density = (2 * edge_count) / (n * (n - 1)) if n > 1 else 0
                cent = {}
                for nid_in in component:
                    deg = sum(1 for e in self._edges.values() if e.source_id == nid_in or (e.bidirectional and e.target_id == nid_in))
                    cent[nid_in] = deg / max(len(component) - 1, 1)
                community = GraphCommunity(id=str(uuid.uuid4()), org_id="", name=f"Community {len(communities) + 1}", node_ids=list(component), edge_count=edge_count, density=round(density, 4), centrality_scores=cent)
                communities.append(community)
        for c in communities:
            self._communities[c.id] = c
        self._save()
        return communities

    def get_node_centrality(self, node_id: str) -> dict:
        node = self._nodes.get(node_id)
        if not node:
            return {}
        degree = 0
        for edge in self._edges.values():
            if edge.source_id == node_id or (edge.bidirectional and edge.target_id == node_id):
                degree += 1
        n = len(self._nodes)
        return {
            "node_id": node_id,
            "name": node.name,
            "degree": degree,
            "degree_centrality": round(degree / max(n - 1, 1), 4),
            "neighbor_count": len([e for e in self._edges.values() if e.source_id == node_id or e.target_id == node_id]),
        }

    def run_graph_query(self, query_type: str, params: dict) -> list:
        if query_type == "get_node":
            n = self._nodes.get(params.get("node_id", ""))
            return [n.to_dict()] if n else []
        elif query_type == "get_neighbors":
            return self.get_neighbors(params.get("node_id", ""), depth=params.get("depth", 1))
        elif query_type == "find_path":
            gp = self.find_shortest_path(params.get("source_id", ""), params.get("target_id", ""))
            return [gp.to_dict()]
        elif query_type == "search":
            return [n.to_dict() for n in self.search_nodes(params.get("query", ""))]
        return []

    def get_graph_analytics(self, org_id: str) -> GraphAnalytics:
        nodes = [n for n in self._nodes.values() if n.org_id == org_id]
        edges = [e for e in self._edges.values() if any(n.id == e.source_id or n.id == e.target_id for n in nodes)]
        by_type = defaultdict(int)
        by_rel = defaultdict(int)
        for n in nodes:
            by_type[n.entity_type.value] += 1
        for e in edges:
            by_rel[e.relation_type.value] += 1
        total_deg = sum(len([e for e in edges if e.source_id == n.id or e.target_id == n.id]) for n in nodes)
        n_count = len(nodes)
        e_count = len(edges)
        ga = GraphAnalytics(
            id=str(uuid.uuid4()), org_id=org_id,
            total_nodes=n_count, total_edges=e_count,
            by_entity_type=dict(by_type), by_relation_type=dict(by_rel),
            avg_degree=round(total_deg / max(n_count, 1), 4),
            density=round((2 * e_count) / max(n_count * (n_count - 1), 1), 6),
            connected_components=len(self.detect_communities()),
        )
        return ga

    def export_graph(self, format: str = "json") -> dict:
        return {
            "nodes": {k: v.to_dict() for k, v in self._nodes.items()},
            "edges": {k: v.to_dict() for k, v in self._edges.items()},
            "stats": {"total_nodes": len(self._nodes), "total_edges": len(self._edges)},
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
