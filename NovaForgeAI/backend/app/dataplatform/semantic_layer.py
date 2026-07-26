"""Semantic Layer module for NovaForge Data Platform & Knowledge Fabric."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class OntologyDomain(Enum):
    REPOSITORY = "repository"
    ENGINEERING = "engineering"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    DATA = "data"
    AI = "ai"
    INFRASTRUCTURE = "infrastructure"
    GOVERNANCE = "governance"


class SemanticRelation(Enum):
    IS_A = "is_a"
    HAS_A = "has_a"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    SAME_AS = "same_as"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    CONTAINS = "contains"
    DERIVES = "derives"


class ReasoningType(Enum):
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"
    ABDUCTIVE = "abductive"
    TRANSITIVE = "transitive"
    HIERARCHICAL = "hierarchical"
    SIMILARITY = "similarity"


class SemanticStatus(Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    REVIEW = "review"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class OntologyClass:
    id: str
    org_id: str
    domain: OntologyDomain
    name: str
    description: str = ""
    parent_class: str = ""
    properties: list = field(default_factory=list)
    relations: list = field(default_factory=list)
    status: SemanticStatus = SemanticStatus.ACTIVE
    version: str = "1.0.0"
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OntologyClass":
        data = data.copy()
        data["domain"] = OntologyDomain(data.get("domain", "data"))
        data["status"] = SemanticStatus(data.get("status", "active"))
        return cls(**data)


@dataclass
class OntologyInstance:
    id: str
    org_id: str
    class_id: str
    name: str
    description: str = ""
    properties: dict = field(default_factory=dict)
    relations: list = field(default_factory=list)
    status: SemanticStatus = SemanticStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OntologyInstance":
        data = data.copy()
        data["status"] = SemanticStatus(data.get("status", "active"))
        return cls(**data)


@dataclass
class SemanticTriple:
    id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float = 1.0
    source: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SemanticTriple":
        return cls(**data)


@dataclass
class ReasoningResult:
    id: str
    org_id: str
    type: ReasoningType
    triples_used: int = 0
    triples_derived: int = 0
    inferences: list = field(default_factory=list)
    execution_time_ms: float = 0.0
    status: str = "completed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReasoningResult":
        data = data.copy()
        data["type"] = ReasoningType(data.get("type", "deductive"))
        return cls(**data)


class SemanticLayer:
    def __init__(self, storage_dir: str = "semantic_layer_data"):
        self.storage_dir = storage_dir
        self._classes: dict[str, OntologyClass] = {}
        self._instances: dict[str, OntologyInstance] = {}
        self._triples: dict[str, SemanticTriple] = {}
        self._reasoning_results: dict[str, ReasoningResult] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _classes_path(self) -> str: return os.path.join(self.storage_dir, "classes.json")
    def _instances_path(self) -> str: return os.path.join(self.storage_dir, "instances.json")
    def _triples_path(self) -> str: return os.path.join(self.storage_dir, "triples.json")
    def _reasoning_path(self) -> str: return os.path.join(self.storage_dir, "reasoning.json")

    def _save(self) -> None:
        try:
            with open(self._classes_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._classes.items()}, f, indent=2, default=str)
            with open(self._instances_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._instances.items()}, f, indent=2, default=str)
            with open(self._triples_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._triples.items()}, f, indent=2, default=str)
            with open(self._reasoning_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reasoning_results.items()}, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save semantic layer data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            for path, store, cls in [
                (self._classes_path(), self._classes, OntologyClass),
                (self._instances_path(), self._instances, OntologyInstance),
                (self._triples_path(), self._triples, SemanticTriple),
                (self._reasoning_path(), self._reasoning_results, ReasoningResult),
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
            logger.error("Failed to load semantic layer data: %s", e, exc_info=True)

    def create_class(self, cls: OntologyClass) -> OntologyClass:
        self._telemetry["create_class_calls"] += 1
        self._classes[cls.id] = cls
        self._save()
        logger.info("Created ontology class: %s [%s]", cls.name, cls.domain.value)
        return cls

    def get_class(self, class_id: str) -> Optional[OntologyClass]:
        return self._classes.get(class_id)

    def list_classes(self, org_id: str, domain: Optional[OntologyDomain] = None) -> list[OntologyClass]:
        results = [c for c in self._classes.values() if c.org_id == org_id]
        if domain:
            results = [c for c in results if c.domain == domain]
        return results

    def create_instance(self, instance: OntologyInstance) -> OntologyInstance:
        self._telemetry["create_instance_calls"] += 1
        self._instances[instance.id] = instance
        self._save()
        return instance

    def get_instances(self, class_id: str) -> list[OntologyInstance]:
        return [i for i in self._instances.values() if i.class_id == class_id]

    def add_triple(self, triple: SemanticTriple) -> SemanticTriple:
        self._telemetry["add_triple_calls"] += 1
        self._triples[triple.id] = triple
        self._save()
        return triple

    def query_triples(self, subject_id: Optional[str] = None, predicate: Optional[str] = None, object_id: Optional[str] = None) -> list[SemanticTriple]:
        results = list(self._triples.values())
        if subject_id:
            results = [t for t in results if t.subject_id == subject_id]
        if predicate:
            results = [t for t in results if t.predicate == predicate]
        if object_id:
            results = [t for t in results if t.object_id == object_id]
        return results

    def run_reasoning(self, org_id: str, type: ReasoningType) -> ReasoningResult:
        self._telemetry["run_reasoning_calls"] += 1
        if type == ReasoningType.TRANSITIVE:
            return self.reason_transitive()
        elif type == ReasoningType.HIERARCHICAL:
            return self.reason_hierarchical()
        elif type == ReasoningType.SIMILARITY:
            return self.reason_similarity()
        else:
            return ReasoningResult(id=str(uuid.uuid4()), org_id=org_id, type=type, status="unsupported")

    def reason_transitive(self) -> ReasoningResult:
        start = time.time()
        org_triples = list(self._triples.values())
        inferences = []
        derived = 0
        for t1 in org_triples:
            for t2 in org_triples:
                if t1.object_id == t2.subject_id and t1.predicate == t2.predicate:
                    new_triple = SemanticTriple(
                        id=str(uuid.uuid4()), subject_id=t1.subject_id, predicate=t1.predicate,
                        object_id=t2.object_id, confidence=min(t1.confidence, t2.confidence) * 0.9,
                        source="transitive_reasoning",
                    )
                    if new_triple.id not in self._triples:
                        self._triples[new_triple.id] = new_triple
                        inferences.append(f"{t1.subject_id} --{t1.predicate}--> {t2.object_id}")
                        derived += 1
        elapsed = (time.time() - start) * 1000
        result = ReasoningResult(id=str(uuid.uuid4()), org_id="", type=ReasoningType.TRANSITIVE,
                                 triples_used=len(org_triples), triples_derived=derived,
                                 inferences=inferences[:20], execution_time_ms=round(elapsed, 2))
        self._reasoning_results[result.id] = result
        self._save()
        return result

    def reason_hierarchical(self) -> ReasoningResult:
        start = time.time()
        inferences = []
        derived = 0
        classes = list(self._classes.values())
        for cls in classes:
            if cls.parent_class:
                parent = self._classes.get(cls.parent_class)
                if parent:
                    inferences.append(f"{cls.name} IS_A {parent.name}")
                    derived += 1
        instances = list(self._instances.values())
        for inst in instances:
            parent_cls = self._classes.get(inst.class_id)
            if parent_cls and parent_cls.parent_class:
                grandparent = self._classes.get(parent_cls.parent_class)
                if grandparent:
                    inferences.append(f"{inst.name} IS_A {grandparent.name} (via {parent_cls.name})")
                    derived += 1
        elapsed = (time.time() - start) * 1000
        result = ReasoningResult(id=str(uuid.uuid4()), org_id="", type=ReasoningType.HIERARCHICAL,
                                 triples_used=len(classes) + len(instances), triples_derived=derived,
                                 inferences=inferences[:20], execution_time_ms=round(elapsed, 2))
        self._reasoning_results[result.id] = result
        self._save()
        return result

    def reason_similarity(self) -> ReasoningResult:
        start = time.time()
        inferences = []
        derived = 0
        inst_list = list(self._instances.values())
        for i in range(len(inst_list)):
            for j in range(i + 1, len(inst_list)):
                a, b = inst_list[i], inst_list[j]
                if a.class_id != b.class_id:
                    continue
                shared = set(a.properties.keys()) & set(b.properties.keys())
                if len(shared) >= 2:
                    inferences.append(f"{a.name} SIMILAR_TO {b.name} (shared: {shared})")
                    derived += 1
        elapsed = (time.time() - start) * 1000
        result = ReasoningResult(id=str(uuid.uuid4()), org_id="", type=ReasoningType.SIMILARITY,
                                 triples_used=len(inst_list), triples_derived=derived,
                                 inferences=inferences[:20], execution_time_ms=round(elapsed, 2))
        self._reasoning_results[result.id] = result
        self._save()
        return result

    def classify_entity(self, entity_properties: dict) -> list[dict]:
        self._telemetry["classify_entity_calls"] += 1
        matches = []
        for cls in self._classes.values():
            score = 0.0
            matched_props = []
            for prop in cls.properties:
                if isinstance(prop, dict) and prop.get("name") in entity_properties:
                    score += 1.0
                    matched_props.append(prop["name"])
            if cls.properties:
                score /= len(cls.properties)
            if score > 0:
                matches.append({"class_id": cls.id, "class_name": cls.name, "score": round(score, 4), "matched_properties": matched_props})
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:5]

    def get_ontology_stats(self, org_id: str) -> dict:
        org_classes = [c for c in self._classes.values() if c.org_id == org_id]
        org_instances = [i for i in self._instances.values() if i.org_id == org_id]
        domain_counts = defaultdict(int)
        for c in org_classes:
            domain_counts[c.domain.value] += 1
        return {
            "total_classes": len(org_classes),
            "total_instances": len(org_instances),
            "total_triples": len(self._triples),
            "by_domain": dict(domain_counts),
            "reasoning_results": len(self._reasoning_results),
            "telemetry": dict(self._telemetry),
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
