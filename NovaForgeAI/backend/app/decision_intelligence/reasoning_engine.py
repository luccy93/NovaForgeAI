"""Reasoning Engine — multi-step, repository, architecture, dependency, security, trade-off reasoning."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class ReasoningStep:
    id: str; decision_id: str; step_type: str; content: str
    order: int = 0; data: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ReasoningStep": return cls(**data)

class ReasoningEngine:
    def __init__(self, storage_dir: str = "decision_data/reasoning"):
        self.storage_dir = storage_dir; self._steps: dict[str, ReasoningStep] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "steps.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._steps[k] = ReasoningStep.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._steps.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def add_step(self, decision_id: str, step_type: str, content: str, data: dict = None) -> ReasoningStep:
        order = len([s for s in self._steps.values() if s.decision_id == decision_id]) + 1
        s = ReasoningStep(id=str(uuid.uuid4()), decision_id=decision_id, step_type=step_type, content=content, order=order, data=data or {})
        self._steps[s.id] = s; self._save(); return s

    def get_chain(self, decision_id: str) -> list[ReasoningStep]:
        return sorted([s for s in self._steps.values() if s.decision_id == decision_id], key=lambda s: s.order)

    def get_telemetry(self) -> dict: return {"steps": len(self._steps)}
