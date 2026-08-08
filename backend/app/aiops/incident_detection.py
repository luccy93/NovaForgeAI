"""Incident Detection — failures, leaks, spikes, outages, security, queue congestion, worker crashes."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class IncidentSignal:
    id: str; org_id: str; incident_type: str; severity: str = "medium"
    source: str = ""; message: str = ""; affected_services: list = field(default_factory=list)
    detected_at: float = field(default_factory=time.time); acknowledged: bool = False
    metadata: dict = field(default_factory=dict)

class IncidentDetection:
    def __init__(self, storage_dir: str = "aiops_data/incidents"):
        self.storage_dir = storage_dir; self._signals: dict[str, IncidentSignal] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "signals.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._signals[k] = IncidentSignal(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._signals.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def detect(self, org_id: str, incident_type: str, message: str, severity: str = "medium", source: str = "", affected: list = None) -> IncidentSignal:
        s = IncidentSignal(id=str(uuid.uuid4()), org_id=org_id, incident_type=incident_type, severity=severity, source=source, message=message, affected_services=affected or [])
        self._signals[s.id] = s; self._save(); return s

    def acknowledge(self, signal_id: str) -> bool:
        s = self._signals.get(signal_id)
        if not s: return False
        s.acknowledged = True; self._save(); return True

    def get_active(self, org_id: str) -> list[IncidentSignal]:
        return [s for s in self._signals.values() if s.org_id == org_id and not s.acknowledged]

    def get_telemetry(self) -> dict: return {"total_signals": len(self._signals)}
