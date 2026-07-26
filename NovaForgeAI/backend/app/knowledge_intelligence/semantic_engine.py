"""Semantic Engine — ontology, entity resolution, relationship discovery, classification, concept extraction."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Ontology:
    id: str; org_id: str; name: str; concepts: list = field(default_factory=list); relations: list = field(default_factory=list); version: int = 1; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class SemanticMapping:
    id: str; org_id: str; entity_id: str; concept: str; confidence: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SemanticEngine:
    def __init__(self, storage_dir: str = "knowledge_data/semantic"):
        self.storage_dir = storage_dir; self._ontologies: dict[str, Ontology] = {}; self._mappings: dict[str, SemanticMapping] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _ont_path(self) -> str: return os.path.join(self.storage_dir, "ontologies.json")
    def _map_path(self) -> str: return os.path.join(self.storage_dir, "mappings.json")

    def _load(self) -> None:
        for path, store, cls in [(self._ont_path(), self._ontologies, Ontology), (self._map_path(), self._mappings, SemanticMapping)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls(**v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._ont_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._ontologies.items()}, f, indent=2, default=str)
            with open(self._map_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._mappings.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_ontology(self, org_id: str, name: str, concepts: list = None) -> Ontology:
        o = Ontology(id=str(uuid.uuid4()), org_id=org_id, name=name, concepts=concepts or [])
        self._ontologies[o.id] = o; self._save(); return o

    def map_entity(self, org_id: str, entity_id: str, concept: str, confidence: float = 0.5) -> SemanticMapping:
        m = SemanticMapping(id=str(uuid.uuid4()), org_id=org_id, entity_id=entity_id, concept=concept, confidence=confidence)
        self._mappings[m.id] = m; self._save(); return m

    def resolve(self, org_id: str, concept: str) -> list[SemanticMapping]:
        return [m for m in self._mappings.values() if m.org_id == org_id and m.concept == concept]

    def get_telemetry(self) -> dict: return {"ontologies": len(self._ontologies), "mappings": len(self._mappings)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class LearningSession:
    id: str; org_id: str; source: str; content: str = ""; patterns: list = field(default_factory=list); insights: list = field(default_factory=list); applied: bool = False; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class OrganizationalLearning:
    def __init__(self, storage_dir: str = "knowledge_data/learning"):
        self.storage_dir = storage_dir; self._sessions: dict[str, LearningSession] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._sessions[k] = LearningSession(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, source: str, content: str, patterns: list = None) -> LearningSession:
        s = LearningSession(id=str(uuid.uuid4()), org_id=org_id, source=source, content=content, patterns=patterns or [])
        self._sessions[s.id] = s; self._save(); return s

    def get_insights(self, org_id: str) -> list[LearningSession]:
        return sorted([s for s in self._sessions.values() if s.org_id == org_id], key=lambda s: s.created_at, reverse=True)[:50]

    def get_telemetry(self) -> dict: return {"sessions": len(self._sessions)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class KnowledgeGraphEntity:
    id: str; org_id: str; name: str; kg_type: str; properties: dict = field(default_factory=dict); created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class KnowledgeGraphRelation:
    id: str; org_id: str; source_id: str; target_id: str; relation: str; weight: float = 1.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeGraph:
    def __init__(self, storage_dir: str = "knowledge_data/graph"):
        self.storage_dir = storage_dir; self._nodes: dict[str, KnowledgeGraphEntity] = {}; self._edges: dict[str, KnowledgeGraphRelation] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _node_path(self) -> str: return os.path.join(self.storage_dir, "nodes.json")
    def _edge_path(self) -> str: return os.path.join(self.storage_dir, "edges.json")

    def _load(self) -> None:
        for path, store, cls in [(self._node_path(), self._nodes, KnowledgeGraphEntity), (self._edge_path(), self._edges, KnowledgeGraphRelation)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls(**v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._node_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._nodes.items()}, f, indent=2, default=str)
            with open(self._edge_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._edges.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def add_node(self, org_id: str, name: str, kg_type: str, properties: dict = None) -> KnowledgeGraphEntity:
        n = KnowledgeGraphEntity(id=str(uuid.uuid4()), org_id=org_id, name=name, kg_type=kg_type, properties=properties or {})
        self._nodes[n.id] = n; self._save(); return n

    def add_edge(self, org_id: str, source_id: str, target_id: str, relation: str) -> Optional[KnowledgeGraphRelation]:
        if source_id not in self._nodes or target_id not in self._nodes: return None
        e = KnowledgeGraphRelation(id=str(uuid.uuid4()), org_id=org_id, source_id=source_id, target_id=target_id, relation=relation)
        self._edges[e.id] = e; self._save(); return e

    def get_neighbors(self, node_id: str) -> list[KnowledgeGraphRelation]:
        return [e for e in self._edges.values() if e.source_id == node_id or e.target_id == node_id]

    def get_telemetry(self) -> dict: return {"nodes": len(self._nodes), "edges": len(self._edges)}
