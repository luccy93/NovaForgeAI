"""Knowledge Engine — core knowledge management, entities, relationships, classification, versioning."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class KnowledgeEntity:
    id: str; org_id: str; name: str; entity_type: str; description: str = ""
    properties: dict = field(default_factory=dict); tags: list = field(default_factory=list)
    version: int = 1; is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntity": return cls(**data)

@dataclass
class KnowledgeRelationship:
    id: str; org_id: str; source_id: str; target_id: str; relation_type: str
    properties: dict = field(default_factory=dict); weight: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeEngine:
    def __init__(self, storage_dir: str = "knowledge_data"):
        self.storage_dir = storage_dir; self._entities: dict[str, KnowledgeEntity] = {}
        self._relationships: dict[str, KnowledgeRelationship] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _ent_path(self) -> str: return os.path.join(self.storage_dir, "entities.json")
    def _rel_path(self) -> str: return os.path.join(self.storage_dir, "relationships.json")

    def _load(self) -> None:
        for path, store, cls in [(self._ent_path(), self._entities, KnowledgeEntity), (self._rel_path(), self._relationships, KnowledgeRelationship)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._ent_path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._entities.items()}, f, indent=2, default=str)
            with open(self._rel_path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._relationships.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_entity(self, org_id: str, name: str, entity_type: str, description: str = "", properties: dict = None) -> KnowledgeEntity:
        e = KnowledgeEntity(id=str(uuid.uuid4()), org_id=org_id, name=name, entity_type=entity_type, description=description, properties=properties or {})
        self._entities[e.id] = e; self._save(); return e

    def add_relationship(self, org_id: str, source_id: str, target_id: str, relation_type: str) -> Optional[KnowledgeRelationship]:
        if source_id not in self._entities or target_id not in self._entities: return None
        r = KnowledgeRelationship(id=str(uuid.uuid4()), org_id=org_id, source_id=source_id, target_id=target_id, relation_type=relation_type)
        self._relationships[r.id] = r; self._save(); return r

    def get_entity(self, entity_id: str) -> Optional[KnowledgeEntity]: return self._entities.get(entity_id)

    def get_relationships(self, entity_id: str) -> list[KnowledgeRelationship]:
        return [r for r in self._relationships.values() if r.source_id == entity_id or r.target_id == entity_id]

    def search_entities(self, org_id: str, query: str) -> list[KnowledgeEntity]:
        q = query.lower()
        return [e for e in self._entities.values() if e.org_id == org_id and (q in e.name.lower() or q in e.description.lower())]

    def get_telemetry(self) -> dict: return {"entities": len(self._entities), "relationships": len(self._relationships)}
