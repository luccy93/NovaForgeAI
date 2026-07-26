"""Enterprise Operations — maintenance windows, emergency mode, DR, regional failover, business continuity."""
import json, uuid, os, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MaintenanceWindow:
    id: str; org_id: str; title: str; description: str = ""
    start_at: str = ""; end_at: str = ""; status: str = "scheduled"
    affected_services: list = field(default_factory=list); approved_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "MaintenanceWindow": return cls(**data)

class EnterpriseOperations:
    def __init__(self, storage_dir: str = "aiops_data/enterprise"):
        self.storage_dir = storage_dir; self._windows: dict[str, MaintenanceWindow] = {}
        self._mode: str = "normal"  # normal, emergency, read_only
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "windows.json")
    def _mode_path(self) -> str: return os.path.join(self.storage_dir, "mode.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._windows[k] = MaintenanceWindow.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)
        if os.path.exists(self._mode_path()):
            try:
                with open(self._mode_path(), "r") as f: self._mode = json.load(f).get("mode", "normal")
            except Exception as e: logger.error("Mode load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._windows.items()}, f, indent=2, default=str)
            with open(self._mode_path(), "w") as f:
                json.dump({"mode": self._mode}, f, indent=2)
        except Exception as e: logger.error("Save error: %s", e)

    def schedule_maintenance(self, org_id: str, title: str, start_at: str, end_at: str, services: list = None) -> MaintenanceWindow:
        w = MaintenanceWindow(id=str(uuid.uuid4()), org_id=org_id, title=title, start_at=start_at, end_at=end_at, affected_services=services or [])
        self._windows[w.id] = w; self._save(); return w

    def set_mode(self, mode: str) -> str:
        self._mode = mode; self._save(); return self._mode

    def get_mode(self) -> str: return self._mode

    def get_telemetry(self) -> dict: return {"maintenance_windows": len(self._windows), "mode": self._mode}
