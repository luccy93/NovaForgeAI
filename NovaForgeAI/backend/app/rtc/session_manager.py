"""Session Manager — collaboration sessions, join/leave, state, history, recovery."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CollabSession:
    id: str; org_id: str; session_type: str  # chat, review, whiteboard, meeting, planning, agent
    name: str = ""; room: str = ""; participants: list = field(default_factory=list)
    state: dict = field(default_factory=dict); is_active: bool = True
    started_at: float = field(default_factory=time.time); ended_at: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self); return d
    @classmethod
    def from_dict(cls, data: dict) -> "CollabSession": return cls(**data)

class SessionManager:
    def __init__(self, storage_dir: str = "rtc_data/sessions"):
        self.storage_dir = storage_dir; self._sessions: dict[str, CollabSession] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._sessions[k] = CollabSession.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, session_type: str, name: str = "", room: str = "") -> CollabSession:
        s = CollabSession(id=str(uuid.uuid4()), org_id=org_id, session_type=session_type, name=name, room=room)
        self._sessions[s.id] = s; self._save(); return s

    def join(self, session_id: str, user_id: str) -> Optional[CollabSession]:
        s = self._sessions.get(session_id)
        if not s: return None
        if user_id not in s.participants: s.participants.append(user_id); self._save()
        return s

    def leave(self, session_id: str, user_id: str) -> Optional[CollabSession]:
        s = self._sessions.get(session_id)
        if not s: return None
        if user_id in s.participants: s.participants.remove(user_id); self._save()
        return s

    def end(self, session_id: str) -> Optional[CollabSession]:
        s = self._sessions.get(session_id)
        if not s: return None
        s.is_active = False; s.ended_at = time.time(); self._save(); return s

    def get_active(self, org_id: str) -> list[CollabSession]:
        return [s for s in self._sessions.values() if s.org_id == org_id and s.is_active]
