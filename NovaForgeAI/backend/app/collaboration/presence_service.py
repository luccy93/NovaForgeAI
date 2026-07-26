"""Presence Service — track online users, current repo, file, agent, task, branch, deployment, session across the platform in real time."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Presence:
    user_id: str
    org_id: str
    status: str = "online"
    current_repository: str = ""
    current_file: str = ""
    current_agent: str = ""
    current_task: str = ""
    current_branch: str = ""
    current_deployment: str = ""
    current_session: str = ""
    last_activity: str = ""
    device: str = ""
    ip_address: str = ""
    metadata: dict = field(default_factory=dict)
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Presence":
        return cls(**data)


@dataclass
class PresenceEvent:
    id: str
    user_id: str
    event_type: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "PresenceEvent": return cls(**data)


class PresenceService:
    def __init__(self, storage_dir: str = "collab_data/presence"):
        self.storage_dir = storage_dir
        self._presences: dict[str, Presence] = {}
        self._events: list[PresenceEvent] = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _presence_path(self) -> str: return os.path.join(self.storage_dir, "presences.json")
    def _events_path(self) -> str: return os.path.join(self.storage_dir, "events.json")

    def _load(self) -> None:
        for path, store in [(self._presence_path(), self._presences), (self._events_path(), None)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if store is not None:
                        for k, v in data.items():
                            try: store[k] = Presence.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._events = [PresenceEvent.from_dict(e) if isinstance(e, dict) else e for e in data]
                except Exception as e: logger.error("Failed to load presence data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._presence_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._presences.items()}, f, indent=2, default=str)
            with open(self._events_path(), "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in self._events[-1000:]], f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save presence data: %s", e)

    def update_presence(self, user_id: str, org_id: str, updates: dict) -> Presence:
        presence = self._presences.get(user_id)
        if not presence:
            presence = Presence(user_id=user_id, org_id=org_id)
            self._presences[user_id] = presence
        for k, v in updates.items():
            if hasattr(presence, k): setattr(presence, k, v)
        presence.last_seen = datetime.now(timezone.utc).isoformat()
        presence.updated_at = presence.last_seen
        self._presences[user_id] = presence
        self._events.append(PresenceEvent(id=str(uuid.uuid4()), user_id=user_id, event_type="presence_update", data=updates))
        self._save()
        return presence

    def set_online(self, user_id: str, org_id: str, session_id: str = "", device: str = "") -> Presence:
        return self.update_presence(user_id, org_id, {"status": "online", "current_session": session_id, "device": device})

    def set_offline(self, user_id: str) -> Optional[Presence]:
        p = self._presences.get(user_id)
        if p:
            p.status = "offline"
            p.last_seen = datetime.now(timezone.utc).isoformat()
            self._save()
        return p

    def set_away(self, user_id: str) -> Optional[Presence]:
        p = self._presences.get(user_id)
        if p:
            p.status = "away"
            p.last_seen = datetime.now(timezone.utc).isoformat()
            self._save()
        return p

    def get_presence(self, user_id: str) -> Optional[Presence]: return self._presences.get(user_id)

    def get_online_users(self, org_id: str = "") -> list[Presence]:
        results = [p for p in self._presences.values() if p.status == "online"]
        if org_id: results = [p for p in results if p.org_id == org_id]
        return results

    def get_collaborators(self, repository: str = "", file: str = "") -> list[Presence]:
        results = list(self._presences.values())
        if repository: results = [p for p in results if p.current_repository == repository]
        if file: results = [p for p in results if p.current_file == file]
        return [p for p in results if p.status == "online"]

    def get_recent_events(self, limit: int = 50) -> list[PresenceEvent]:
        return self._events[-limit:]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
