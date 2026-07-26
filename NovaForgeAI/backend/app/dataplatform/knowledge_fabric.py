import json
import uuid
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class FabricNodeType(Enum):
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
    MESSAGE = "message"
    COMMIT = "commit"
    PR = "pr"
    ISSUE = "issue"
    SECURITY_FINDING = "security_finding"
    DEPLOYMENT = "deployment"
    TEST = "test"


class FabricRelationshipType(Enum):
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


class FabricSource(Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    JIRA = "jira"
    LINEAR = "linear"
    SLACK = "slack"
    NOTION = "notion"
    CONFLUENCE = "confluence"
    GOOGLE_DRIVE = "google_drive"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    REST_API = "rest_api"
    MANUAL = "manual"
    SYSTEM = "system"
    API_DOC = "api_doc"
    SECURITY_SCAN = "security_scan"


class FabricEntityStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"
    DELETED = "deleted"
    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass
class FabricNode:
    id: str
    org_id: str
    node_type: FabricNodeType
    name: str
    qualified_name: str
    description: str = ""
    source: FabricSource = FabricSource.MANUAL
    status: FabricEntityStatus = FabricEntityStatus.ACTIVE
    properties: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["node_type"] = self.node_type.value
        d["source"] = self.source.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FabricNode":
        data = data.copy()
        data["node_type"] = FabricNodeType(data.get("node_type", "module"))
        data["source"] = FabricSource(data.get("source", "manual"))
        data["status"] = FabricEntityStatus(data.get("status", "active"))
        return cls(**data)


@dataclass
class FabricRelationship:
    id: str
    source_id: str
    target_id: str
    relationship_type: FabricRelationshipType
    properties: dict = field(default_factory=dict)
    weight: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relationship_type"] = self.relationship_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FabricRelationship":
        data = data.copy()
        data["relationship_type"] = FabricRelationshipType(data.get("relationship_type", "depends_on"))
        return cls(**data)


@dataclass
class FabricSubgraph:
    id: str
    org_id: str
    name: str
    description: str = ""
    nodes: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FabricSubgraph":
        return cls(**data)


@dataclass
class FabricSnapshot:
    id: str
    org_id: str
    total_nodes: int = 0
    total_relationships: int = 0
    by_type: dict = field(default_factory=dict)
    by_source: dict = field(default_factory=dict)
    by_status: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FabricSnapshot":
        return cls(**data)


class KnowledgeFabric:
    def __init__(self, storage_dir: str = "fabric_data"):
        self.storage_dir = storage_dir
        self._nodes: dict[str, FabricNode] = {}
        self._relationships: dict[str, FabricRelationship] = {}
        self._subgraphs: dict[str, FabricSubgraph] = {}
        self._snapshots: dict[str, FabricSnapshot] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _nodes_path(self) -> str:
        return os.path.join(self.storage_dir, "nodes.json")

    def _relationships_path(self) -> str:
        return os.path.join(self.storage_dir, "relationships.json")

    def _subgraphs_path(self) -> str:
        return os.path.join(self.storage_dir, "subgraphs.json")

    def _snapshots_path(self) -> str:
        return os.path.join(self.storage_dir, "snapshots.json")

    def _save(self) -> None:
        try:
            nodes_data = {nid: n.to_dict() for nid, n in self._nodes.items()}
            with open(self._nodes_path(), "w", encoding="utf-8") as f:
                json.dump(nodes_data, f, indent=2, default=str)

            rels_data = {rid: r.to_dict() for rid, r in self._relationships.items()}
            with open(self._relationships_path(), "w", encoding="utf-8") as f:
                json.dump(rels_data, f, indent=2, default=str)

            subs_data = {sid: s.to_dict() for sid, s in self._subgraphs.items()}
            with open(self._subgraphs_path(), "w", encoding="utf-8") as f:
                json.dump(subs_data, f, indent=2, default=str)

            snaps_data = {sid: s.to_dict() for sid, s in self._snapshots.items()}
            with open(self._snapshots_path(), "w", encoding="utf-8") as f:
                json.dump(snaps_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save fabric data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._nodes_path()):
                with open(self._nodes_path(), "r", encoding="utf-8") as f:
                    nodes_data = json.load(f)
                for nid, data in nodes_data.items():
                    try:
                        self._nodes[nid] = FabricNode.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed node %s: %s", nid, e)

            if os.path.exists(self._relationships_path()):
                with open(self._relationships_path(), "r", encoding="utf-8") as f:
                    rels_data = json.load(f)
                for rid, data in rels_data.items():
                    try:
                        self._relationships[rid] = FabricRelationship.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed relationship %s: %s", rid, e)

            if os.path.exists(self._subgraphs_path()):
                with open(self._subgraphs_path(), "r", encoding="utf-8") as f:
                    subs_data = json.load(f)
                for sid, data in subs_data.items():
                    try:
                        self._subgraphs[sid] = FabricSubgraph.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed subgraph %s: %s", sid, e)

            if os.path.exists(self._snapshots_path()):
                with open(self._snapshots_path(), "r", encoding="utf-8") as f:
                    snaps_data = json.load(f)
                for sid, data in snaps_data.items():
                    try:
                        self._snapshots[sid] = FabricSnapshot.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed snapshot %s: %s", sid, e)
        except Exception as e:
            logger.error("Failed to load fabric data: %s", e, exc_info=True)

    def add_node(self, node: FabricNode) -> FabricNode:
        self._telemetry["add_node_calls"] += 1
        if not node.id:
            node.id = str(uuid.uuid4())
        if not node.created_at:
            node.created_at = datetime.now(timezone.utc).isoformat()
        if not node.updated_at:
            node.updated_at = node.created_at
        self._nodes[node.id] = node
        self._save()
        logger.info("Added fabric node %s: %s (%s)", node.id, node.name, node.node_type.value)
        return node

    def get_node(self, node_id: str) -> Optional[FabricNode]:
        self._telemetry["get_node_calls"] += 1
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, updates: dict) -> Optional[FabricNode]:
        self._telemetry["update_node_calls"] += 1
        node = self._nodes.get(node_id)
        if not node:
            logger.warning("Attempted to update unknown node: %s", node_id)
            return None
        for key, value in updates.items():
            if hasattr(node, key) and key not in ("id", "created_at"):
                if key == "node_type":
                    setattr(node, key, FabricNodeType(value) if isinstance(value, str) else value)
                elif key == "source":
                    setattr(node, key, FabricSource(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(node, key, FabricEntityStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(node, key, value)
        node.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated fabric node: %s", node_id)
        return node

    def delete_node(self, node_id: str) -> bool:
        self._telemetry["delete_node_calls"] += 1
        node = self._nodes.get(node_id)
        if not node:
            logger.warning("Attempted to delete unknown node: %s", node_id)
            return False
        node.status = FabricEntityStatus.DELETED
        node.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Soft-deleted fabric node: %s", node_id)
        return True

    def search_nodes(self, query: str, node_type: Optional[FabricNodeType] = None) -> list[FabricNode]:
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

    def list_nodes(self, org_id: str, node_type: Optional[FabricNodeType] = None, status: Optional[FabricEntityStatus] = None) -> list[FabricNode]:
        self._telemetry["list_nodes_calls"] += 1
        results = []
        for node in self._nodes.values():
            if node.org_id != org_id:
                continue
            if node_type and node.node_type != node_type:
                continue
            if status and node.status != status:
                continue
            results.append(node)
        return results

    def add_relationship(self, rel: FabricRelationship) -> FabricRelationship:
        self._telemetry["add_relationship_calls"] += 1
        if not rel.id:
            rel.id = str(uuid.uuid4())
        if not rel.created_at:
            rel.created_at = datetime.now(timezone.utc).isoformat()
        self._relationships[rel.id] = rel
        self._save()
        logger.info("Added fabric relationship %s: %s -> %s (%s)", rel.id, rel.source_id, rel.target_id, rel.relationship_type.value)
        return rel

    def get_relationships(self, node_id: str) -> list[FabricRelationship]:
        self._telemetry["get_relationships_calls"] += 1
        return [
            rel for rel in self._relationships.values()
            if rel.source_id == node_id or rel.target_id == node_id
        ]

    def get_neighbors(self, node_id: str, depth: int = 1) -> list[dict]:
        self._telemetry["get_neighbors_calls"] += 1
        visited = {node_id}
        queue = deque([(node_id, 0)])
        neighbors = []

        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for rel in self._relationships.values():
                neighbor_id = None
                edge_direction = None
                if rel.source_id == current_id:
                    neighbor_id = rel.target_id
                    edge_direction = "outgoing"
                elif rel.target_id == current_id:
                    neighbor_id = rel.source_id
                    edge_direction = "incoming"
                if neighbor_id and neighbor_id not in visited:
                    visited.add(neighbor_id)
                    neighbor_node = self._nodes.get(neighbor_id)
                    neighbors.append({
                        "node": neighbor_node.to_dict() if neighbor_node else {"id": neighbor_id},
                        "relationship": rel.to_dict(),
                        "direction": edge_direction,
                        "depth": current_depth + 1,
                    })
                    queue.append((neighbor_id, current_depth + 1))

        return neighbors

    def find_path(self, source_id: str, target_id: str) -> list[dict]:
        self._telemetry["find_path_calls"] += 1
        if source_id == target_id:
            return []

        visited = {source_id}
        queue = deque([[source_id]])

        while queue:
            path = queue.popleft()
            current_id = path[-1]
            for rel in self._relationships.values():
                neighbor_id = None
                if rel.source_id == current_id:
                    neighbor_id = rel.target_id
                elif rel.target_id == current_id:
                    neighbor_id = rel.source_id
                if neighbor_id and neighbor_id not in visited:
                    new_path = path + [neighbor_id]
                    if neighbor_id == target_id:
                        result = []
                        for i in range(len(new_path) - 1):
                            from_id = new_path[i]
                            to_id = new_path[i + 1]
                            found_rel = next(
                                (r for r in self._relationships.values()
                                 if (r.source_id == from_id and r.target_id == to_id) or
                                    (r.source_id == to_id and r.target_id == from_id)),
                                None
                            )
                            from_node = self._nodes.get(from_id)
                            to_node = self._nodes.get(to_id)
                            result.append({
                                "from": from_node.to_dict() if from_node else {"id": from_id},
                                "to": to_node.to_dict() if to_node else {"id": to_id},
                                "relationship": found_rel.to_dict() if found_rel else {},
                            })
                        return result
                    visited.add(neighbor_id)
                    queue.append(new_path)

        return []

    def create_subgraph(self, subgraph: FabricSubgraph) -> FabricSubgraph:
        self._telemetry["create_subgraph_calls"] += 1
        if not subgraph.id:
            subgraph.id = str(uuid.uuid4())
        subgraph.created_at = datetime.now(timezone.utc).isoformat()
        self._subgraphs[subgraph.id] = subgraph
        self._save()
        logger.info("Created fabric subgraph %s: %s", subgraph.id, subgraph.name)
        return subgraph

    def get_fabric_stats(self, org_id: str) -> dict:
        self._telemetry["get_fabric_stats_calls"] += 1
        org_nodes = [n for n in self._nodes.values() if n.org_id == org_id]
        org_rels = [r for r in self._relationships.values()
                    if any(n.id == r.source_id or n.id == r.target_id for n in org_nodes)]

        by_type: dict[str, int] = defaultdict(int)
        by_source: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        for n in org_nodes:
            by_type[n.node_type.value] += 1
            by_source[n.source.value] += 1
            by_status[n.status.value] += 1

        by_relationship_type: dict[str, int] = defaultdict(int)
        for r in org_rels:
            by_relationship_type[r.relationship_type.value] += 1

        return {
            "org_id": org_id,
            "total_nodes": len(org_nodes),
            "total_relationships": len(org_rels),
            "by_type": dict(by_type),
            "by_source": dict(by_source),
            "by_status": dict(by_status),
            "by_relationship_type": dict(by_relationship_type),
        }

    def snapshot(self, org_id: str) -> FabricSnapshot:
        self._telemetry["snapshot_calls"] += 1
        org_nodes = [n for n in self._nodes.values() if n.org_id == org_id]
        org_rels = [r for r in self._relationships.values()
                    if any(n.id == r.source_id or n.id == r.target_id for n in org_nodes)]

        by_type: dict[str, int] = defaultdict(int)
        by_source: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        for n in org_nodes:
            by_type[n.node_type.value] += 1
            by_source[n.source.value] += 1
            by_status[n.status.value] += 1

        snap = FabricSnapshot(
            id=str(uuid.uuid4()),
            org_id=org_id,
            total_nodes=len(org_nodes),
            total_relationships=len(org_rels),
            by_type=dict(by_type),
            by_source=dict(by_source),
            by_status=dict(by_status),
        )
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
