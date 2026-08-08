"""Webhook Engine — receive, validate, process, and dispatch webhooks from all integrated services."""
import json, uuid, os, logging, hmac, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WebhookStatus(Enum):
    RECEIVED = "received"
    VALIDATED = "validated"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookDelivery:
    id: str
    source: str
    event_type: str
    payload: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    signature: str = ""
    status: WebhookStatus = WebhookStatus.RECEIVED
    verified: bool = False
    retry_count: int = 0
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookDelivery":
        data = data.copy()
        data["status"] = WebhookStatus(data.get("status", "received"))
        return cls(**data)


@dataclass
class WebhookEndpoint:
    id: str
    url: str
    secret: str = ""
    events: list = field(default_factory=list)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["secret"] = "***" if self.secret else ""
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookEndpoint": return cls(**data)


class WebhookEngine:
    def __init__(self, storage_dir: str = "integration_data/webhooks"):
        self.storage_dir = storage_dir
        self._deliveries: dict[str, WebhookDelivery] = {}
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._handlers: dict[str, callable] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _del_path(self) -> str: return os.path.join(self.storage_dir, "deliveries.json")
    def _ep_path(self) -> str: return os.path.join(self.storage_dir, "endpoints.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._del_path(), self._deliveries, WebhookDelivery),
            (self._ep_path(), self._endpoints, WebhookEndpoint),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load webhook data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._del_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._deliveries.items()}, f, indent=2, default=str)
            with open(self._ep_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._endpoints.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save webhook data: %s", e)

    def register_endpoint(self, url: str, secret: str = "", events: list = None) -> WebhookEndpoint:
        ep = WebhookEndpoint(id=str(uuid.uuid4()), url=url, secret=secret, events=events or [])
        self._endpoints[ep.id] = ep
        self._save()
        return ep

    def receive(self, source: str, event_type: str, payload: dict, headers: dict = None, signature: str = "") -> WebhookDelivery:
        delivery = WebhookDelivery(id=str(uuid.uuid4()), source=source, event_type=event_type, payload=payload, headers=headers or {}, signature=signature)
        self._deliveries[delivery.id] = delivery
        self._telemetry["webhooks_received"] = self._telemetry.get("webhooks_received", 0) + 1
        self._save()
        self._process(delivery)
        return delivery

    def verify_signature(self, delivery_id: str, secret: str) -> bool:
        delivery = self._deliveries.get(delivery_id)
        if not delivery: return False
        expected = hmac.new(secret.encode(), json.dumps(delivery.payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()
        verified = hmac.compare_digest(expected, delivery.signature)
        delivery.verified = verified
        delivery.status = WebhookStatus.VALIDATED if verified else WebhookStatus.FAILED
        self._save()
        return verified

    def register_handler(self, event_type: str, handler) -> None:
        self._handlers[event_type] = handler

    def _process(self, delivery: WebhookDelivery) -> None:
        delivery.status = WebhookStatus.PROCESSING
        handler = self._handlers.get(delivery.event_type)
        if handler:
            try:
                handler(delivery)
                delivery.status = WebhookStatus.COMPLETED
            except Exception as e:
                delivery.status = WebhookStatus.FAILED
                delivery.error = str(e)
                logger.error("Webhook processing failed: %s", e)
        else:
            delivery.status = WebhookStatus.COMPLETED
        delivery.processed_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def get_deliveries(self, source: str = "", status: Optional[WebhookStatus] = None, limit: int = 100) -> list[WebhookDelivery]:
        results = list(self._deliveries.values())
        if source: results = [d for d in results if d.source == source]
        if status: results = [d for d in results if d.status == status]
        return sorted(results, key=lambda d: d.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
