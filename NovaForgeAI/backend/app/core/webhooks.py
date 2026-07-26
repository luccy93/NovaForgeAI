"""Webhook system — management, delivery, retry, dead letter queue."""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.redis import get_redis


class WebhookDeliveryStatus:
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class WebhookService:
    """Manages webhook endpoints, delivery, retry with exponential backoff, and DLQ."""

    RETRY_MAX_ATTEMPTS = 5
    RETRY_BACKOFF_BASE = 30
    DEAD_LETTER_TTL = 86400 * 30

    @staticmethod
    def sign_payload(payload: dict, secret: str) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def verify_signature(payload: dict, signature: str, secret: str) -> bool:
        expected = WebhookService.sign_payload(payload, secret)
        return hmac.compare_digest(expected, signature)

    @staticmethod
    async def deliver(
        webhook_id: str,
        url: str,
        event_type: str,
        payload: dict,
        secret: Optional[str] = None,
    ) -> dict:
        body = {
            "event": event_type,
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": webhook_id,
            "X-Webhook-Event": event_type,
            "X-Webhook-Timestamp": body["timestamp"],
        }
        if secret:
            signature = WebhookService.sign_payload(body, secret)
            headers["X-Webhook-Signature"] = signature

        attempt = 0
        last_error = None

        while attempt < WebhookService.RETRY_MAX_ATTEMPTS:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=body, headers=headers)
                if 200 <= resp.status_code < 300:
                    delivery = {
                        "status": WebhookDeliveryStatus.DELIVERED,
                        "attempts": attempt,
                        "status_code": resp.status_code,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    await WebhookService._record_delivery(webhook_id, delivery)
                    return delivery
                last_error = f"HTTP {resp.status_code}"
            except Exception as e:
                last_error = str(e)

            if attempt < WebhookService.RETRY_MAX_ATTEMPTS:
                delay = WebhookService.RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                await asyncio.sleep(min(delay, 300))

        delivery = {
            "status": WebhookDeliveryStatus.DEAD_LETTER,
            "attempts": attempt,
            "error": last_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await WebhookService._record_delivery(webhook_id, delivery)
        await WebhookService._dead_letter(webhook_id, body, last_error)
        return delivery

    @staticmethod
    async def _record_delivery(webhook_id: str, delivery: dict) -> None:
        try:
            redis = await get_redis()
            key = f"webhook:delivery:{webhook_id}"
            await redis.lpush(key, json.dumps(delivery))
            await redis.ltrim(key, 0, 99)
            await redis.expire(key, 86400 * 7)
        except Exception:
            pass

    @staticmethod
    async def _dead_letter(webhook_id: str, payload: dict, error: str) -> None:
        try:
            redis = await get_redis()
            entry = {
                "webhook_id": webhook_id,
                "payload": payload,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.lpush("webhook:dead_letter", json.dumps(entry))
            await redis.ltrim("webhook:dead_letter", 0, 999)
        except Exception:
            pass

    @staticmethod
    async def get_delivery_log(webhook_id: str, limit: int = 20) -> list[dict]:
        try:
            redis = await get_redis()
            raw = await redis.lrange(f"webhook:delivery:{webhook_id}", 0, limit - 1)
            return [json.loads(item) for item in raw]
        except Exception:
            return []

    @staticmethod
    async def get_dead_letter_queue(limit: int = 50) -> list[dict]:
        try:
            redis = await get_redis()
            raw = await redis.lrange("webhook:dead_letter", 0, limit - 1)
            return [json.loads(item) for item in raw]
        except Exception:
            return []

    @staticmethod
    async def retry_dead_letter(index: int) -> dict:
        try:
            redis = await get_redis()
            raw = await redis.lrange("webhook:dead_letter", 0, -1)
            if index < len(raw):
                entry = json.loads(raw[index])
                result = await WebhookService.deliver(
                    entry["webhook_id"],
                    entry["payload"].get("url", ""),
                    entry["payload"].get("event", "unknown"),
                    entry["payload"].get("payload", {}),
                )
                if result["status"] == WebhookDeliveryStatus.DELIVERED:
                    await redis.lrem("webhook:dead_letter", 1, raw[index])
                return result
            return {"status": "not_found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


webhook_service = WebhookService()
