"""Data Lineage — track data flow, lineage graphs, impact analysis, and provenance for the Data Platform & Knowledge Fabric."""

import json
import uuid
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class LineageNodeType(Enum):
    DATA_SOURCE = "data_source"
    TRANSFORMATION = "transformation"
    EMBEDDING = "embedding"
    SEARCH_PIPELINE = "search_pipeline"
    AI_OUTPUT = "ai_output"
    REPORT = "report"
    ANALYTICS = "analytics"
    AGENT_DECISION = "agent_decision"
    DATASET = "dataset"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    EXPORT = "export"
    API_ENDPOINT = "api_endpoint"
    CACHE = "cache"


class LineageRelationType(Enum):
    PRODUCES = "produces"
    CONSUMES = "consumes"
    TRANSFORMS = "transforms"
    DERIVES = "derives"
    COPIES = "copies"
    AGGREGATES = "aggregates"
    FILTERS = "filters"
    JOINS = "joins"
    VALIDATES = "validates"
    ENRICHES = "enriches"


class LineageStatus(Enum):
    ACTIVE = "active"
    STALE = "stale"
    ERROR = "error"
    DISABLED = "disabled"


class LineageLevel(Enum):
    TABLE = "table"
    COLUMN = "column"
    FIELD = "field"
    FILE = "file"
    RECORD = "record"
    STREAM = "stream"


@dataclass
class LineageNode:
    id: str
    org_id: str
    workspace_id: str
    node_type: LineageNodeType
    name: str
    qualified_name: str
    description: str = ""
    level: LineageLevel = LineageLevel.TABLE
    schema: dict = field(default_factory=dict)
    status: LineageStatus = LineageStatus.ACTIVE
    source: str = ""
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["node_type"] = self.node_type.value
        d["level"] = self.level.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LineageNode":
        data = data.copy()
        data["node_type"] = LineageNodeType(data.get("node_type", "dataset"))
        data["level"] = LineageLevel(data.get("level", "table"))
        data["status"] = LineageStatus(data.get("status", "active"))
        return cls(**data)


@dataclass
class LineageEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: LineageRelationType
    transformation_details: str = ""
    confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relation_type"] = self.relation_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LineageEdge":
        data = data.copy()
        data["relation_type"] = LineageRelationType(data.get("relation_type", "produces"))
        return cls(**data)


@dataclass
class LineageProvenance:
    id: str
    node_id: str
    timestamp: str
    action: str
    actor: str
    details: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LineageProvenance":
        return cls(**data)


@dataclass
class LineageGraph:
    id: str
    org_id: str
    name: str
    description: str = ""
    nodes: list[str] = field(default_factory=list)
    edges: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LineageGraph":
        return cls(**data)


class DataLineage:
    def __init__(self, storage_dir: str = "lineage_data"):
        self.storage_dir = storage_dir
        self._nodes: dict[str, LineageNode] = {}
        self._edges: dict[str, LineageEdge] = {}
        self._provenance: dict[str, LineageProvenance] = {}
        self._lineage_graphs: dict[str, LineageGraph] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _nodes_path(self) -> str:
        return os.path.join(self.storage_dir, "lineage_nodes.json")

    def _edges_path(self) -> str:
        return os.path.join(self.storage_dir, "lineage_edges.json")

    def _provenance_path(self) -> str:
        return os.path.join(self.storage_dir, "lineage_provenance.json")

    def _graphs_path(self) -> str:
        return os.path.join(self.storage_dir, "lineage_graphs.json")

    def _save(self) -> None:
        try:
            nodes_data = {nid: n.to_dict() for nid, n in self._nodes.items()}
            with open(self._nodes_path(), "w", encoding="utf-8") as f:
                json.dump(nodes_data, f, indent=2, default=str)

            edges_data = {eid: e.to_dict() for eid, e in self._edges.items()}
            with open(self._edges_path(), "w", encoding="utf-8") as f:
                json.dump(edges_data, f, indent=2, default=str)

            prov_data = {pid: p.to_dict() for pid, p in self._provenance.items()}
            with open(self._provenance_path(), "w", encoding="utf-8") as f:
                json.dump(prov_data, f, indent=2, default=str)

            graphs_data = {gid: g.to_dict() for gid, g in self._lineage_graphs.items()}
            with open(self._graphs_path(), "w", encoding="utf-8") as f:
                json.dump(graphs_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save lineage data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._nodes_path()):
                with open(self._nodes_path(), "r", encoding="utf-8") as f:
                    nodes_data = json.load(f)
                for nid, data in nodes_data.items():
                    try:
                        self._nodes[nid] = LineageNode.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed lineage node %s: %s", nid, e)

            if os.path.exists(self._edges_path()):
                with open(self._edges_path(), "r", encoding="utf-8") as f:
                    edges_data = json.load(f)
                for eid, data in edges_data.items():
                    try:
                        self._edges[eid] = LineageEdge.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed lineage edge %s: %s", eid, e)

            if os.path.exists(self._provenance_path()):
                with open(self._provenance_path(), "r", encoding="utf-8") as f:
                    prov_data = json.load(f)
                for pid, data in prov_data.items():
                    try:
                        self._provenance[pid] = LineageProvenance.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed provenance record %s: %s", pid, e)

            if os.path.exists(self._graphs_path()):
                with open(self._graphs_path(), "r", encoding="utf-8") as f:
                    graphs_data = json.load(f)
                for gid, data in graphs_data.items():
                    try:
                        self._lineage_graphs[gid] = LineageGraph.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed lineage graph %s: %s", gid, e)
        except Exception as e:
            logger.error("Failed to load lineage data: %s", e, exc_info=True)

    def register_node(self, node: LineageNode) -> LineageNode:
        self._telemetry["register_node_calls"] += 1
        if not node.id:
            node.id = str(uuid.uuid4())
        if not node.created_at:
            node.created_at = datetime.now(timezone.utc).isoformat()
        if not node.updated_at:
            node.updated_at = node.created_at
        self._nodes[node.id] = node
        self._save()
        logger.info("Registered lineage node %s: %s (%s)", node.id, node.name, node.node_type.value)
        return node

    def get_node(self, node_id: str) -> Optional[LineageNode]:
        self._telemetry["get_node_calls"] += 1
        return self._nodes.get(node_id)

    def search_nodes(self, query: str, node_type: Optional[LineageNodeType] = None) -> list[LineageNode]:
        self._telemetry["search_nodes_calls"] += 1
        results = []
        q = query.lower()
        for node in self._nodes.values():
            if node_type and node.node_type != node_type:
                continue
            if q in node.name.lower() or q in node.qualified_name.lower() or q in node.description.lower():
                results.append(node)
            elif any(q in tag.lower() for tag in node.tags):
                results.append(node)
        return results

    def add_edge(self, edge: LineageEdge) -> LineageEdge:
        self._telemetry["add_edge_calls"] += 1
        if not edge.id:
            edge.id = str(uuid.uuid4())
        if not edge.created_at:
            edge.created_at = datetime.now(timezone.utc).isoformat()
        self._edges[edge.id] = edge
        self._save()
        logger.info("Added lineage edge %s: %s -> %s (%s)", edge.id, edge.source_id, edge.target_id, edge.relation_type.value)
        return edge

    def get_upstream(self, node_id: str, depth: int = 5) -> list[dict]:
        self._telemetry["get_upstream_calls"] += 1
        visited = {node_id}
        queue = deque([(node_id, 0)])
        upstream = []

        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self._edges.values():
                if edge.target_id == current_id:
                    source_id = edge.source_id
                    if source_id not in visited:
                        visited.add(source_id)
                        source_node = self._nodes.get(source_id)
                        upstream.append({
                            "node": source_node.to_dict() if source_node else {"id": source_id},
                            "edge": edge.to_dict(),
                            "direction": "upstream",
                            "depth": current_depth + 1,
                        })
                        queue.append((source_id, current_depth + 1))

        return upstream

    def get_downstream(self, node_id: str, depth: int = 5) -> list[dict]:
        self._telemetry["get_downstream_calls"] += 1
        visited = {node_id}
        queue = deque([(node_id, 0)])
        downstream = []

        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self._edges.values():
                if edge.source_id == current_id:
                    target_id = edge.target_id
                    if target_id not in visited:
                        visited.add(target_id)
                        target_node = self._nodes.get(target_id)
                        downstream.append({
                            "node": target_node.to_dict() if target_node else {"id": target_id},
                            "edge": edge.to_dict(),
                            "direction": "downstream",
                            "depth": current_depth + 1,
                        })
                        queue.append((target_id, current_depth + 1))

        return downstream

    def get_full_lineage(self, node_id: str, depth: int = 5) -> dict:
        self._telemetry["get_full_lineage_calls"] += 1
        node = self._nodes.get(node_id)
        return {
            "node": node.to_dict() if node else {"id": node_id},
            "upstream": self.get_upstream(node_id, depth),
            "downstream": self.get_downstream(node_id, depth),
        }

    def record_provenance(self, provenance: LineageProvenance) -> LineageProvenance:
        self._telemetry["record_provenance_calls"] += 1
        if not provenance.id:
            provenance.id = str(uuid.uuid4())
        if not provenance.created_at:
            provenance.created_at = datetime.now(timezone.utc).isoformat()
        self._provenance[provenance.id] = provenance
        self._save()
        logger.info("Recorded provenance %s for node %s: %s by %s", provenance.id, provenance.node_id, provenance.action, provenance.actor)
        return provenance

    def get_node_history(self, node_id: str, days: int = 90) -> list[LineageProvenance]:
        self._telemetry["get_node_history_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []
        for prov in self._provenance.values():
            if prov.node_id != node_id:
                continue
            try:
                prov_time = datetime.fromisoformat(prov.timestamp)
                if prov_time >= cutoff:
                    results.append(prov)
            except (ValueError, TypeError):
                results.append(prov)
        return sorted(results, key=lambda p: p.timestamp, reverse=True)

    def create_lineage_graph(self, graph: LineageGraph) -> LineageGraph:
        self._telemetry["create_lineage_graph_calls"] += 1
        if not graph.id:
            graph.id = str(uuid.uuid4())
        graph.created_at = datetime.now(timezone.utc).isoformat()
        self._lineage_graphs[graph.id] = graph
        self._save()
        logger.info("Created lineage graph %s: %s", graph.id, graph.name)
        return graph

    def impact_analysis(self, node_id: str) -> dict:
        self._telemetry["impact_analysis_calls"] += 1
        node = self._nodes.get(node_id)
        downstream = self.get_downstream(node_id, depth=10)
        upstream = self.get_upstream(node_id, depth=1)

        affected_nodes = []
        for entry in downstream:
            affected_nodes.append(entry["node"])

        downstream_edge_count = len(downstream)
        downstream_node_count = len(affected_nodes)

        by_type: dict[str, int] = defaultdict(int)
        for n in affected_nodes:
            nt = n.get("node_type", "unknown")
            by_type[nt] += 1

        return {
            "target_node": node.to_dict() if node else {"id": node_id},
            "total_downstream_nodes": downstream_node_count,
            "total_downstream_edges": downstream_edge_count,
            "upstream_dependencies": len(upstream),
            "affected_by_type": dict(by_type),
            "impact_summary": (
                f"Changes to '{node.name if node else node_id}' will affect {downstream_node_count} downstream "
                f"assets across {len(by_type)} types and depend on {len(upstream)} upstream sources."
            ),
        }

    def get_lineage_stats(self, org_id: str) -> dict:
        self._telemetry["get_lineage_stats_calls"] += 1
        org_nodes = [n for n in self._nodes.values() if n.org_id == org_id]
        org_edges = [e for e in self._edges.values()
                     if any(n.id == e.source_id or n.id == e.target_id for n in org_nodes)]

        by_node_type: dict[str, int] = defaultdict(int)
        by_level: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        by_relation: dict[str, int] = defaultdict(int)

        for n in org_nodes:
            by_node_type[n.node_type.value] += 1
            by_level[n.level.value] += 1
            by_status[n.status.value] += 1

        for e in org_edges:
            by_relation[e.relation_type.value] += 1

        return {
            "org_id": org_id,
            "total_nodes": len(org_nodes),
            "total_edges": len(org_edges),
            "by_node_type": dict(by_node_type),
            "by_level": dict(by_level),
            "by_status": dict(by_status),
            "by_relation_type": dict(by_relation),
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
