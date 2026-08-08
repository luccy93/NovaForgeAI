"""Real-Time Gateway — WebSocket/SSE connections, rooms, channels, heartbeat, pub/sub."""
import json, uuid, os, logging, asyncio, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class RealtimeGateway:
    def __init__(self):
        self._connections: dict[str, dict] = {}
        self._rooms: dict[str, list[str]] = {}
        self._handlers: dict[str, list[Callable]] = {}
        self._telemetry: dict = {"connections": 0, "messages": 0, "errors": 0}

    async def connect(self, connection_id: str, user_id: str, metadata: dict = None) -> str:
        cid = connection_id or str(uuid.uuid4())
        self._connections[cid] = {"user_id": user_id, "connected_at": time.time(), "metadata": metadata or {}, "rooms": [], "alive": True}
        self._telemetry["connections"] += 1
        return cid

    async def disconnect(self, connection_id: str) -> bool:
        conn = self._connections.pop(connection_id, None)
        if conn:
            for room in conn.get("rooms", []):
                if room in self._rooms and connection_id in self._rooms[room]:
                    self._rooms[room].remove(connection_id)
            return True
        return False

    async def join_room(self, connection_id: str, room: str) -> bool:
        if connection_id not in self._connections: return False
        if room not in self._rooms: self._rooms[room] = []
        if connection_id not in self._rooms[room]: self._rooms[room].append(connection_id)
        if room not in self._connections[connection_id]["rooms"]: self._connections[connection_id]["rooms"].append(room)
        return True

    async def leave_room(self, connection_id: str, room: str) -> bool:
        if room in self._rooms and connection_id in self._rooms[room]:
            self._rooms[room].remove(connection_id)
        # prevent KeyError
        conn = self._connections.get(connection_id)
        if conn and room in conn["rooms"]: conn["rooms"].remove(room)
        return True

    async def publish(self, room: str, event: str, data: dict) -> int:
        if room not in self._rooms: return 0
        message = {"event": event, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
        count = 0
        for cid in self._rooms[room]:
            conn = self._connections.get(cid)
            if conn and conn.get("alive"):
                count += 1
                self._telemetry["messages"] += 1
        return count

    async def broadcast(self, event: str, data: dict) -> int:
        count = 0
        for cid, conn in self._connections.items():
            if conn.get("alive"): count += 1
        self._telemetry["messages"] += count
        return count

    def on(self, event: str, handler: Callable):
        if event not in self._handlers: self._handlers[event] = []
        self._handlers[event].append(handler)

    def get_telemetry(self) -> dict: return dict(self._telemetry)

    def get_room_members(self, room: str) -> list[dict]:
        members = []
        for cid in self._rooms.get(room, []):
            conn = self._connections.get(cid)
            if conn: members.append({"connection_id": cid, "user_id": conn["user_id"], "metadata": conn["metadata"]})
        return members
