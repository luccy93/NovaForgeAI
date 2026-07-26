"""Evidence Engine — source files, functions, classes, line numbers, commits, metrics, security reports."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class Evidence:
    id: str; decision_id: str; source: str; evidence_type: str  # file, function, class, commit, metric, security_report, graph_rel, doc_ref
    location: str = ""; content: Any = None; confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Evidence": return cls(**data)

class EvidenceEngine:
    def __init__(self, storage_dir: str = "decision_data/evidence"):
        self.storage_dir = storage_dir; self._evidence: dict[str, Evidence] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "evidence.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._evidence[k] = Evidence.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._evidence.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def add(self, decision_id: str, source: str, evidence_type: str, location: str = "", content: Any = None) -> Evidence:
        e = Evidence(id=str(uuid.uuid4()), decision_id=decision_id, source=source, evidence_type=evidence_type, location=location, content=content)
        self._evidence[e.id] = e; self._save(); return e

    def get_by_decision(self, decision_id: str) -> list[Evidence]:
        return [e for e in self._evidence.values() if e.decision_id == decision_id]

    def get_telemetry(self) -> dict: return {"total_evidence": len(self._evidence)}
