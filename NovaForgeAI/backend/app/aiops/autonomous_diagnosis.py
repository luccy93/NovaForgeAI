"""Autonomous Diagnosis — analyze logs, metrics, tracing, repo changes, infra events, deployments."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Diagnosis:
    id: str; org_id: str; target: str; diagnosis_type: str
    findings: list = field(default_factory=list); severity: str = "info"
    confidence: float = 0.0; recommendations: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Diagnosis": return cls(**data)

class AutonomousDiagnosis:
    def __init__(self, storage_dir: str = "aiops_data/diagnosis"):
        self.storage_dir = storage_dir; self._diagnoses: dict[str, Diagnosis] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "diagnoses.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._diagnoses[k] = Diagnosis.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._diagnoses.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def diagnose(self, org_id: str, target: str, diagnosis_type: str, findings: list = None, recommendations: list = None, confidence: float = 0.0, severity: str = "info") -> Diagnosis:
        d = Diagnosis(id=str(uuid.uuid4()), org_id=org_id, target=target, diagnosis_type=diagnosis_type, findings=findings or [], recommendations=recommendations or [], confidence=confidence, severity=severity)
        self._diagnoses[d.id] = d; self._save(); return d

    def get_recent(self, org_id: str, limit: int = 50) -> list[Diagnosis]:
        return sorted([d for d in self._diagnoses.values() if d.org_id == org_id], key=lambda d: d.created_at, reverse=True)[:limit]
