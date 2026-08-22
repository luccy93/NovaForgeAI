"""Message service — conversation management, visibility enforcement, edit history (Volume 54)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.support.constants import MessageVisibility, SenderType

logger = logging.getLogger(__name__)


class MessageService:
    def __init__(self):
        self._messages: dict[str, dict] = {}
        self._telemetry = {"created": 0, "edited": 0}

    def create_message(
        self,
        ticket_id: str,
        sender_id: str,
        message_text: str,
        sender_type: str = "customer",
        visibility: str = "customer",
        attachments: Optional[list[dict]] = None,
        ai_generated: bool = False,
        ai_confidence: Optional[float] = None,
        ai_citations: Optional[list[dict]] = None,
    ) -> dict:
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        vis = MessageVisibility(visibility) if visibility in [e.value for e in MessageVisibility] else MessageVisibility.CUSTOMER
        message = {
            "id": message_id,
            "ticket_id": ticket_id,
            "sender_id": sender_id,
            "sender_type": sender_type,
            "message_text": message_text,
            "visibility": vis.value,
            "attachments": attachments or [],
            "edited_at": None,
            "edit_history": [],
            "ai_generated": ai_generated,
            "ai_confidence": ai_confidence,
            "ai_citations": ai_citations or [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._messages[message_id] = message
        self._telemetry["created"] += 1
        return message

    def get_message(self, message_id: str) -> Optional[dict]:
        return self._messages.get(message_id)

    def list_messages(
        self,
        ticket_id: str,
        visibility_filter: Optional[str] = None,
        include_internal: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        results = [m for m in self._messages.values() if m["ticket_id"] == ticket_id]
        if not include_internal:
            results = [m for m in results if m["visibility"] != MessageVisibility.INTERNAL.value]
        elif visibility_filter:
            results = [m for m in results if m["visibility"] == visibility_filter]
        results.sort(key=lambda m: m["created_at"])
        return results[offset:offset + limit]

    def edit_message(self, message_id: str, new_text: str, editor_id: str) -> Optional[dict]:
        message = self._messages.get(message_id)
        if not message:
            return None
        now = datetime.now(timezone.utc)
        message["edit_history"].append({
            "previous_text": message["message_text"],
            "edited_by": editor_id,
            "edited_at": now.isoformat(),
        })
        message["message_text"] = new_text
        message["edited_at"] = now.isoformat()
        message["updated_at"] = now.isoformat()
        self._telemetry["edited"] += 1
        return message

    def get_customer_messages(self, ticket_id: str, limit: int = 100) -> list[dict]:
        return self.list_messages(ticket_id, include_internal=False, limit=limit)

    def get_internal_messages(self, ticket_id: str, limit: int = 100) -> list[dict]:
        results = [m for m in self._messages.values()
                   if m["ticket_id"] == ticket_id and m["visibility"] == MessageVisibility.INTERNAL.value]
        results.sort(key=lambda m: m["created_at"])
        return results[:limit]

    def count_messages(self, ticket_id: str) -> int:
        return sum(1 for m in self._messages.values() if m["ticket_id"] == ticket_id)

    def has_customer_response(self, ticket_id: str) -> bool:
        return any(
            m["ticket_id"] == ticket_id and m["sender_type"] == SenderType.CUSTOMER.value
            for m in self._messages.values()
        )

    def get_last_message(self, ticket_id: str) -> Optional[dict]:
        msgs = [m for m in self._messages.values() if m["ticket_id"] == ticket_id]
        if not msgs:
            return None
        return max(msgs, key=lambda m: m["created_at"])

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


message_service = MessageService()
