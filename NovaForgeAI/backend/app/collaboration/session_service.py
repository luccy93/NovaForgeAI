"""Session Service — manage user sessions, workspace sessions, collaboration sessions, session analytics."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Session:
    id: str
    user_id: str
    org_id: str
    workspace_id: str = ""
    session_type: str = "active"
    ip_address: str = ""
    device: str = ""
    user_agent: str = ""
    is_active: bool = True
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str = ""
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def duration_minutes(self) -> float:
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.ended_at) if self.ended_at else datetime.now(timezone.utc)
        return (end - start).total_seconds() / 60

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Session": return cls(**data)


class SessionService:
    def __init__(self, storage_dir: str = "collab_data/sessions"):
        self.storage_dir = storage_dir
        self._sessions: dict[str, Session] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._sessions[k] = Session.from_dict(v)
                    except Exception as e: logger.warning("Skipping session %s: %s", k, e)
            except Exception as e: logger.error("Failed to load sessions: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save sessions: %s", e)

    def start_session(self, user_id: str, org_id: str, workspace_id: str = "", device: str = "", ip_address: str = "", user_agent: str = "") -> Session:
        session = Session(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, workspace_id=workspace_id, device=device, ip_address=ip_address, user_agent=user_agent)
        self._sessions[session.id] = session
        self._save()
        return session

    def end_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session: return False
        session.is_active = False
        session.ended_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def get_session(self, session_id: str) -> Optional[Session]: return self._sessions.get(session_id)

    def get_active_sessions(self, user_id: str = "", org_id: str = "") -> list[Session]:
        results = [s for s in self._sessions.values() if s.is_active]
        if user_id: results = [s for s in results if s.user_id == user_id]
        if org_id: results = [s for s in results if s.org_id == org_id]
        return results

    def get_user_sessions(self, user_id: str, limit: int = 50) -> list[Session]:
        results = [s for s in self._sessions.values() if s.user_id == user_id]
        return sorted(results, key=lambda s: s.started_at, reverse=True)[:limit]

    def update_activity(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session: return False
        session.last_activity = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
