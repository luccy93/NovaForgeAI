"""Knowledge Learning — learn from incidents, deployments, failures, rollbacks, security events, performance."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class LearnedInsight:
    id: str; org_id: str; source: str; insight: str; action: str = ""
    confidence: float = 0.0; applied_count: int = 0; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "LearnedInsight": return cls(**data)

class KnowledgeLearning:
    def __init__(self, storage_dir: str = "aiops_data/learning"):
        self.storage_dir = storage_dir; self._insights: dict[str, LearnedInsight] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "insights.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._insights[k] = LearnedInsight.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._insights.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def learn(self, org_id: str, source: str, insight: str, action: str = "", confidence: float = 0.0) -> LearnedInsight:
        li = LearnedInsight(id=str(uuid.uuid4()), org_id=org_id, source=source, insight=insight, action=action, confidence=confidence)
        self._insights[li.id] = li; self._save(); return li

    def get_applicable(self, org_id: str, source: str = "") -> list[LearnedInsight]:
        results = [i for i in self._insights.values() if i.org_id == org_id]
        if source: results = [i for i in results if i.source == source]
        return sorted(results, key=lambda i: i.confidence, reverse=True)

    def get_telemetry(self) -> dict: return {"insights": len(self._insights)}
