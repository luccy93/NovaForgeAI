"""Live Collaboration — shared sessions, architecture reviews, live docs, prompt editing, planning."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class LiveSession:
    id: str; org_id: str; session_type: str; title: str  # ai_chat, repo_analysis, arch_review, doc_edit, prompt_edit, agent_monitor, workflow, planning
    participants: list = field(default_factory=list); state: dict = field(default_factory=dict)
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "LiveSession": return cls(**data)

class LiveCollaboration:
    def __init__(self, storage_dir: str = "rtc_data/live"):
        self.storage_dir = storage_dir; self._sessions: dict[str, LiveSession] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._sessions[k] = LiveSession.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def start(self, org_id: str, session_type: str, title: str) -> LiveSession:
        s = LiveSession(id=str(uuid.uuid4()), org_id=org_id, session_type=session_type, title=title)
        self._sessions[s.id] = s; self._save(); return s

    def join(self, session_id: str, user_id: str) -> Optional[LiveSession]:
        s = self._sessions.get(session_id)
        if not s: return None
        if user_id not in s.participants: s.participants.append(user_id); self._save()
        return s

    def update_state(self, session_id: str, state: dict) -> Optional[LiveSession]:
        s = self._sessions.get(session_id)
        if not s: return None
        s.state.update(state); self._save(); return s

    def end(self, session_id: str) -> Optional[LiveSession]:
        s = self._sessions.get(session_id)
        if not s: return None
        s.is_active = False; self._save(); return s
