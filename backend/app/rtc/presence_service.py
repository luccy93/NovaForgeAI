"""Presence Service — online status, typing indicators, activity tracking, heartbeats."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Presence:
    user_id: str; org_id: str; status: str = "offline"  # online, away, busy, offline
    device: str = "web"; last_seen: float = 0.0; custom_status: str = ""
    typing_in: list = field(default_factory=list)  # active rooms/channels
    metadata: dict = field(default_factory=dict)

class PresenceService:
    def __init__(self):
        self._presence: dict[str, Presence] = {}
        self._telemetry: dict = {"total_presence": 0, "updates": 0}

    def set_presence(self, user_id: str, org_id: str, status: str = "online", device: str = "web", custom_status: str = "") -> Presence:
        p = self._presence.get(user_id)
        if not p:
            p = Presence(user_id=user_id, org_id=org_id, status=status, device=device, last_seen=time.time(), custom_status=custom_status)
            self._presence[user_id] = p
            self._telemetry["total_presence"] += 1
        else:
            p.status = status; p.last_seen = time.time(); p.custom_status = custom_status; p.device = device
        self._telemetry["updates"] += 1
        return p

    def get_presence(self, user_id: str) -> Optional[Presence]: return self._presence.get(user_id)

    def set_typing(self, user_id: str, room: str, is_typing: bool = True) -> None:
        p = self._presence.get(user_id)
        if not p: return
        if is_typing:
            if room not in p.typing_in: p.typing_in.append(room)
        else:
            if room in p.typing_in: p.typing_in.remove(room)

    def get_online_users(self, org_id: str) -> list[Presence]:
        return [p for p in self._presence.values() if p.org_id == org_id and p.status in ("online", "away")]

    def heartbeat(self, user_id: str) -> bool:
        p = self._presence.get(user_id)
        if not p: return False
        p.last_seen = time.time(); return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
