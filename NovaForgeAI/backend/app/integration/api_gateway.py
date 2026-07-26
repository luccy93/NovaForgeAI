"""API Gateway — REST, GraphQL, gRPC gateway with authentication, rate limiting, routing, and versioning for integration APIs."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class GatewayRouteMethod(Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"
    PATCH = "patch"
    GRAPHQL = "graphql"
    GRPC = "grpc"


@dataclass
class GatewayRoute:
    id: str
    path: str
    method: GatewayRouteMethod
    target_service: str
    target_path: str = ""
    auth_required: bool = True
    rate_limit: int = 100
    timeout_ms: int = 30000
    headers: dict = field(default_factory=dict)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["method"] = self.method.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GatewayRoute":
        data = data.copy()
        data["method"] = GatewayRouteMethod(data.get("method", "get"))
        return cls(**data)


@dataclass
class APIKey:
    id: str
    org_id: str
    name: str
    key_hash: str
    scopes: list = field(default_factory=list)
    is_active: bool = True
    expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "APIKey": return cls(**data)


class APIGateway:
    def __init__(self, storage_dir: str = "integration_data/gateway"):
        self.storage_dir = storage_dir
        self._routes: dict[str, GatewayRoute] = {}
        self._api_keys: dict[str, APIKey] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _routes_path(self) -> str: return os.path.join(self.storage_dir, "routes.json")
    def _keys_path(self) -> str: return os.path.join(self.storage_dir, "api_keys.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._routes_path(), self._routes, GatewayRoute),
            (self._keys_path(), self._api_keys, APIKey),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load gateway data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._routes_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._routes.items()}, f, indent=2, default=str)
            with open(self._keys_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._api_keys.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save gateway data: %s", e)

    def add_route(self, path: str, method: GatewayRouteMethod, target_service: str, target_path: str = "", auth_required: bool = True, rate_limit: int = 100) -> GatewayRoute:
        route = GatewayRoute(id=str(uuid.uuid4()), path=path, method=method, target_service=target_service, target_path=target_path or path, auth_required=auth_required, rate_limit=rate_limit)
        self._routes[route.id] = route
        self._save()
        return route

    def remove_route(self, route_id: str) -> bool:
        if route_id not in self._routes: return False
        del self._routes[route_id]
        self._save()
        return True

    def create_api_key(self, org_id: str, name: str, key: str, scopes: list = None) -> APIKey:
        import hashlib
        ak = APIKey(id=str(uuid.uuid4()), org_id=org_id, name=name, key_hash=hashlib.sha256(key.encode()).hexdigest(), scopes=scopes or [])
        self._api_keys[ak.id] = ak
        self._save()
        return ak

    def validate_api_key(self, key: str) -> Optional[APIKey]:
        import hashlib
        kh = hashlib.sha256(key.encode()).hexdigest()
        for ak in self._api_keys.values():
            if ak.key_hash == kh and ak.is_active: return ak
        return None

    def get_routes(self, service: str = "") -> list[GatewayRoute]:
        results = [r for r in self._routes.values() if r.is_active]
        if service: results = [r for r in results if r.target_service == service]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
