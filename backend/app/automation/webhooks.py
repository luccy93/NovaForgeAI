"""Webhook receiver (Volume 33).

Authenticated webhooks trigger workflows. HMAC signing (SHA-256) with
per-tenant secrets; expired/non-signed requests rejected. The receiver
parses common webhook payloads into bus events dispatched by DispatchHub.
"""
import base64, hashlib, hmac, logging, time
from typing import Any, Optional

from .events import AutomationEvent
from .triggers import DispatchHub

logger = logging.getLogger(__name__)


class WebhookError(Exception):
    pass


def sign_payload(secret: str, body: bytes, timestamp: str) -> str:
    message = f"{timestamp}.{body.decode('utf-8', 'replace')}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_signature(secret: str, body: bytes, timestamp: str,
                     signature: str, tolerance_s: int = 300) -> None:
    if not signature:
        raise WebhookError("missing signature")
    now = time.time()
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        raise WebhookError("invalid timestamp")
    if abs(now - ts) > tolerance_s:
        raise WebhookError("webhook timestamp expired")
    expected = sign_payload(secret, body, timestamp)
    if not hmac.compare_digest(expected, signature):
        raise WebhookError("signature mismatch")


class WebhookReceiver:
    """Maps authenticated webhook requests to bus events + dispatch."""

    def __init__(self, secrets: Optional[dict] = None,
                 hub: Optional[DispatchHub] = None,
                 bus=None):
        self.secrets = secrets or {}  # path -> secret
        self.hub = hub or DispatchHub()
        self.bus = bus
        self.received = 0
        self.rejected = 0

    def add_secret(self, path: str, secret: str) -> None:
        self.secrets[path] = secret

    def handle(self, path: str, body: bytes,
               timestamp: str, signature: str) -> dict:
        secret = self.secrets.get(path)
        if secret is None:
            self.rejected += 1
            raise WebhookError(f"no secret registered for {path}")
        verify_signature(secret, body, timestamp, signature)
        self.received += 1
        payload = self._parse(body)
        event = AutomationEvent(topic="request", payload={"path": path,
                                                          **payload})
        if self.bus is not None:
            self.bus.emit("automation.webhook", payload={"path": path,
                                                         "event": event.to_dict()})
        matches = self.hub.dispatch({"kind": "request", "path": path,
                                     "payload": payload})
        return {"received": True, "path": path, "dispatched": matches,
                "event_id": event.event_id}

    def _parse(self, body: bytes) -> dict:
        import json
        try:
            return json.loads(body or b"{}")
        except Exception:
            return {"raw": body.decode("utf-8", "replace")[:2000]}

    def health(self) -> dict:
        return {"received": self.received, "rejected": self.rejected,
                "paths": sorted(self.secrets.keys())}