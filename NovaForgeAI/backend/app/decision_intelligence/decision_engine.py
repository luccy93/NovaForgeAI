"""Decision Engine — core decision orchestration, types, pipeline, publication."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)

class DecisionType(Enum):
    ARCHITECTURE = "architecture"; CODE_REVIEW = "code_review"; REFACTORING = "refactoring"
    SECURITY = "security"; TESTING = "testing"; DEPLOYMENT = "deployment"; DEPENDENCY = "dependency"
    DATABASE = "database"; INFRASTRUCTURE = "infrastructure"; PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"; AGENT_ROUTING = "agent_routing"; PROMPT = "prompt"
    MODEL_SELECTION = "model_selection"

class DecisionStatus(Enum):
    PROPOSED = "proposed"; VALIDATING = "validating"; APPROVED = "approved"; REJECTED = "rejected"
    IMPLEMENTED = "implemented"; ROLLED_BACK = "rolled_back"

@dataclass
class Decision:
    id: str; org_id: str; decision_type: DecisionType; title: str; description: str = ""
    status: DecisionStatus = DecisionStatus.PROPOSED; author_id: str = ""
    evidence: list = field(default_factory=list); reasoning: list = field(default_factory=list)
    confidence: float = 0.0; alternatives: list = field(default_factory=list)
    tradeoffs: dict = field(default_factory=dict); risk_score: float = 0.0
    business_impact: dict = field(default_factory=dict); tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["decision_type"] = self.decision_type.value; d["status"] = self.status.value; return d
    @classmethod
    def from_dict(cls, data: dict) -> "Decision":
        data = data.copy(); data["decision_type"] = DecisionType(data.get("decision_type", "architecture"))
        data["status"] = DecisionStatus(data.get("status", "proposed")); return cls(**data)

class DecisionEngine:
    def __init__(self, storage_dir: str = "decision_data/decisions"):
        self.storage_dir = storage_dir; self._decisions: dict[str, Decision] = {}
        self._telemetry: dict = {"proposed": 0, "approved": 0, "rejected": 0}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "decisions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._decisions[k] = Decision.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._decisions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def propose(self, org_id: str, decision_type: DecisionType, title: str, author_id: str = "", description: str = "") -> Decision:
        d = Decision(id=str(uuid.uuid4()), org_id=org_id, decision_type=decision_type, title=title, author_id=author_id, description=description)
        self._decisions[d.id] = d; self._telemetry["proposed"] += 1; self._save(); return d

    def approve(self, decision_id: str) -> Optional[Decision]:
        d = self._decisions.get(decision_id)
        if not d: return None
        d.status = DecisionStatus.APPROVED; d.updated_at = datetime.now(timezone.utc).isoformat()
        self._telemetry["approved"] += 1; self._save(); return d

    def reject(self, decision_id: str) -> Optional[Decision]:
        d = self._decisions.get(decision_id)
        if not d: return None
        d.status = DecisionStatus.REJECTED; d.updated_at = datetime.now(timezone.utc).isoformat()
        self._telemetry["rejected"] += 1; self._save(); return d

    def get_by_type(self, org_id: str, decision_type: DecisionType) -> list[Decision]:
        return [d for d in self._decisions.values() if d.org_id == org_id and d.decision_type == decision_type]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
