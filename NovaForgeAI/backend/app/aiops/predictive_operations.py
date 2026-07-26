"""Predictive Operations — predict incidents, saturation, exhaustion, bottlenecks, scaling needs."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Prediction:
    id: str; org_id: str; prediction_type: str; target: str; severity: str = "info"
    probability: float = 0.0; estimated_timeframe: str = ""; recommendation: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Prediction": return cls(**data)

class PredictiveOperations:
    def __init__(self, storage_dir: str = "aiops_data/predictions"):
        self.storage_dir = storage_dir; self._predictions: dict[str, Prediction] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "predictions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._predictions[k] = Prediction.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._predictions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def predict(self, org_id: str, pred_type: str, target: str, probability: float = 0.0, timeframe: str = "", recommendation: str = "", severity: str = "info") -> Prediction:
        p = Prediction(id=str(uuid.uuid4()), org_id=org_id, prediction_type=pred_type, target=target, probability=probability, estimated_timeframe=timeframe, recommendation=recommendation, severity=severity)
        self._predictions[p.id] = p; self._save(); return p

    def get_active(self, org_id: str) -> list[Prediction]:
        return sorted([p for p in self._predictions.values() if p.org_id == org_id and p.probability > 0.3], key=lambda p: p.probability, reverse=True)
