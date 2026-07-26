"""Collaborative AI — shared AI sessions, memory, prompts, context, reasoning, citations."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class AISession:
    id: str; org_id: str; name: str; participants: list = field(default_factory=list)
    prompts: list = field(default_factory=list); context: dict = field(default_factory=dict)
    citations: list = field(default_factory=list); reasoning: list = field(default_factory=list)
    repository_id: str = ""; is_shared: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AISession": return cls(**data)

class CollaborativeAI:
    def __init__(self, storage_dir: str = "rtc_data/ai"):
        self.storage_dir = storage_dir; self._sessions: dict[str, AISession] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._sessions[k] = AISession.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_session(self, org_id: str, name: str) -> AISession:
        s = AISession(id=str(uuid.uuid4()), org_id=org_id, name=name)
        self._sessions[s.id] = s; self._save(); return s

    def add_prompt(self, session_id: str, user_id: str, content: str) -> Optional[AISession]:
        s = self._sessions.get(session_id)
        if not s: return None
        s.prompts.append({"user_id": user_id, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()})
        if user_id not in s.participants: s.participants.append(user_id)
        s.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return s

    def set_context(self, session_id: str, context: dict) -> Optional[AISession]:
        s = self._sessions.get(session_id)
        if not s: return None
        s.context.update(context); s.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return s

    def get_active_sessions(self, org_id: str) -> list[AISession]:
        return [s for s in self._sessions.values() if s.org_id == org_id]
