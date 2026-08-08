"""API Explorer — interactive REST/GraphQL explorer with OpenAPI viewer, authentication, request builder, response viewer, code samples, history, collections."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class APIProtocol(Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    WEBSOCKET = "websocket"


@dataclass
class APIRequest:
    id: str
    user_id: str
    name: str
    protocol: APIProtocol = APIProtocol.REST
    method: str = "GET"
    url: str = ""
    headers: dict = field(default_factory=dict)
    body: str = ""
    variables: dict = field(default_factory=dict)
    auth_type: str = "none"
    response_status: int = 0
    response_body: str = ""
    response_time_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["protocol"] = self.protocol.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "APIRequest":
        data = data.copy()
        data["protocol"] = APIProtocol(data.get("protocol", "rest"))
        return cls(**data)


@dataclass
class APICollection:
    id: str
    user_id: str
    name: str
    description: str = ""
    requests: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "APICollection": return cls(**data)


class APIExplorer:
    def __init__(self, storage_dir: str = "dx_data/api_explorer"):
        self.storage_dir = storage_dir
        self._requests: dict[str, APIRequest] = {}
        self._collections: dict[str, APICollection] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _req_path(self) -> str: return os.path.join(self.storage_dir, "requests.json")
    def _col_path(self) -> str: return os.path.join(self.storage_dir, "collections.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._req_path(), self._requests, APIRequest),
            (self._col_path(), self._collections, APICollection),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load API explorer: %s", e)

    def _save(self) -> None:
        try:
            with open(self._req_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._requests.items()}, f, indent=2, default=str)
            with open(self._col_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._collections.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save API explorer: %s", e)

    def save_request(self, user_id: str, name: str, method: str, url: str, headers: dict = None, body: str = "", auth_type: str = "none") -> APIRequest:
        req = APIRequest(id=str(uuid.uuid4()), user_id=user_id, name=name, method=method, url=url, headers=headers or {}, body=body, auth_type=auth_type)
        self._requests[req.id] = req
        self._save()
        return req

    def record_response(self, request_id: str, status: int, body: str, time_ms: float) -> bool:
        req = self._requests.get(request_id)
        if not req: return False
        req.response_status = status
        req.response_body = body[:5000]
        req.response_time_ms = time_ms
        self._save()
        return True

    def create_collection(self, user_id: str, name: str, description: str = "") -> APICollection:
        col = APICollection(id=str(uuid.uuid4()), user_id=user_id, name=name, description=description)
        self._collections[col.id] = col
        self._save()
        return col

    def add_to_collection(self, collection_id: str, request_id: str) -> bool:
        col = self._collections.get(collection_id)
        if not col: return False
        if request_id not in col.requests: col.requests.append(request_id)
        self._save()
        return True

    def get_history(self, user_id: str, limit: int = 50) -> list[APIRequest]:
        results = [r for r in self._requests.values() if r.user_id == user_id]
        return sorted(results, key=lambda r: r.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
