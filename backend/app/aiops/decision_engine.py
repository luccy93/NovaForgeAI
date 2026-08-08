"""Decision Engine — risk, confidence, business impact, downtime, dependencies, approval, safety."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Decision:
    id: str; org_id: str; action_id: str; decision: str = "pending"
    risk_score: float = 0.0; confidence: float = 0.0; business_impact: str = "low"
    estimated_downtime_seconds: int = 0; requires_approval: bool = False
    approved_by: str = ""; safety_passed: bool = True; reasoning: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Decision": return cls(**data)

class DecisionEngine:
    def __init__(self, storage_dir: str = "aiops_data/decisions"):
        self.storage_dir = storage_dir; self._decisions: dict[str, Decision] = {}
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

    def evaluate(self, org_id: str, action_id: str, risk: float = 0.0, confidence: float = 0.0, impact: str = "low", downtime: int = 0) -> Decision:
        d = Decision(id=str(uuid.uuid4()), org_id=org_id, action_id=action_id, risk_score=risk, confidence=confidence, business_impact=impact, estimated_downtime_seconds=downtime, requires_approval=risk > 0.5 or impact == "critical")
        d.decision = "approved" if not d.requires_approval else "pending_review"
        self._decisions[d.id] = d; self._save(); return d

    def approve(self, decision_id: str, user_id: str) -> Optional[Decision]:
        d = self._decisions.get(decision_id)
        if not d: return None
        d.decision = "approved"; d.approved_by = user_id; self._save(); return d

    def reject(self, decision_id: str, user_id: str) -> Optional[Decision]:
        d = self._decisions.get(decision_id)
        if not d: return None
        d.decision = "rejected"; d.approved_by = user_id; self._save(); return d
