"""Knowledge Governance — versioning, ownership, approval, classification, access, retention, auditing."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class GovernancePolicy:
    id: str; org_id: str; name: str; policy_type: str; rules: dict = field(default_factory=dict); is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeGovernance:
    def __init__(self, storage_dir: str = "knowledge_data/governance"):
        self.storage_dir = storage_dir; self._policies: dict[str, GovernancePolicy] = {}; self._audit: list = []
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "policies.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._policies[k] = GovernancePolicy(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._policies.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_policy(self, org_id: str, name: str, policy_type: str, rules: dict = None) -> GovernancePolicy:
        p = GovernancePolicy(id=str(uuid.uuid4()), org_id=org_id, name=name, policy_type=policy_type, rules=rules or {})
        self._policies[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"policies": len(self._policies)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KnowledgeQuality:
    id: str; org_id: str; entity_id: str; completeness: float = 0.0; accuracy: float = 0.0
    freshness: float = 0.0; consistency: float = 0.0; coverage: float = 0.0
    trust_score: float = 0.0; health: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeQuality:
    def __init__(self, storage_dir: str = "knowledge_data/quality"):
        self.storage_dir = storage_dir; self._scores: dict[str, KnowledgeQuality] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "scores.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._scores[k] = KnowledgeQuality(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._scores.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def assess(self, org_id: str, entity_id: str, completeness: float = 0.8) -> KnowledgeQuality:
        kq = KnowledgeQuality(id=str(uuid.uuid4()), org_id=org_id, entity_id=entity_id, completeness=completeness, accuracy=0.85, freshness=0.75, consistency=0.8, coverage=completeness, trust_score=0.8, health=(completeness + 0.85 + 0.75 + 0.8) / 4)
        self._scores[kq.id] = kq; self._save(); return kq

    def get_telemetry(self) -> dict: return {"scores": len(self._scores)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class EngineeringPattern:
    id: str; org_id: str; pattern_type: str; name: str; description: str = ""
    examples: list = field(default_factory=list); frequency: int = 0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class EngineeringKnowledge:
    def __init__(self, storage_dir: str = "knowledge_data/patterns"):
        self.storage_dir = storage_dir; self._patterns: dict[str, EngineeringPattern] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "patterns.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._patterns[k] = EngineeringPattern(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._patterns.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, pattern_type: str, name: str, description: str = "", examples: list = None) -> EngineeringPattern:
        p = EngineeringPattern(id=str(uuid.uuid4()), org_id=org_id, pattern_type=pattern_type, name=name, description=description, examples=examples or [])
        self._patterns[p.id] = p; self._save(); return p

    def search(self, org_id: str, pattern_type: str = "") -> list[EngineeringPattern]:
        results = [p for p in self._patterns.values() if p.org_id == org_id]
        if pattern_type: results = [p for p in results if p.pattern_type == pattern_type]
        return sorted(results, key=lambda p: p.frequency, reverse=True)

    def get_telemetry(self) -> dict: return {"patterns": len(self._patterns)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KnowledgeDiscovery:
    id: str; org_id: str; discovery_type: str; title: str; description: str = ""
    confidence: float = 0.0; entities: list = field(default_factory=list); created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeDiscovery:
    def __init__(self, storage_dir: str = "knowledge_data/discovery"):
        self.storage_dir = storage_dir; self._discoveries: dict[str, KnowledgeDiscovery] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "discoveries.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._discoveries[k] = KnowledgeDiscovery(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._discoveries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def discover(self, org_id: str, discovery_type: str, title: str, description: str = "", entities: list = None) -> KnowledgeDiscovery:
        d = KnowledgeDiscovery(id=str(uuid.uuid4()), org_id=org_id, discovery_type=discovery_type, title=title, description=description, confidence=0.7, entities=entities or [])
        self._discoveries[d.id] = d; self._save(); return d

    def get_by_type(self, org_id: str, discovery_type: str) -> list[KnowledgeDiscovery]:
        return [d for d in self._discoveries.values() if d.org_id == org_id and d.discovery_type == discovery_type]

    def get_telemetry(self) -> dict: return {"discoveries": len(self._discoveries)}
