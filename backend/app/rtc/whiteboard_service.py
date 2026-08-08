"""Whiteboard Service — sketches, diagrams, collaborative editing, version history."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Whiteboard:
    id: str; org_id: str; title: str; ws_type: str = "sketch"
    elements: list = field(default_factory=list); participants: list = field(default_factory=list)
    version: int = 1; is_locked: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Whiteboard": return cls(**data)

class WhiteboardService:
    def __init__(self, storage_dir: str = "rtc_data/whiteboards"):
        self.storage_dir = storage_dir; self._boards: dict[str, Whiteboard] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "whiteboards.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._boards[k] = Whiteboard.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._boards.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, title: str, ws_type: str = "sketch") -> Whiteboard:
        b = Whiteboard(id=str(uuid.uuid4()), org_id=org_id, title=title, ws_type=ws_type)
        self._boards[b.id] = b; self._save(); return b

    def add_element(self, board_id: str, element: dict) -> Optional[Whiteboard]:
        b = self._boards.get(board_id)
        if not b: return None
        b.elements.append(element); b.version += 1; b.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return b

    def get_telemetry(self) -> dict: return {"boards": len(self._boards)}
