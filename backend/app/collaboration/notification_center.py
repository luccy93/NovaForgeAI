"""Notification Center — deliver mentions, assignments, AI reports, repository changes, deployment status, security alerts, approval requests, workspace updates."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    MENTION = "mention"
    ASSIGNMENT = "assignment"
    AI_REPORT = "ai_report"
    REPOSITORY_CHANGE = "repository_change"
    DEPLOYMENT_STATUS = "deployment_status"
    SECURITY_ALERT = "security_alert"
    APPROVAL_REQUEST = "approval_request"
    WORKSPACE_UPDATE = "workspace_update"
    REVIEW_REQUEST = "review_request"
    DISCUSSION_REPLY = "discussion_reply"


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    id: str
    org_id: str
    user_id: str
    notification_type: NotificationType
    title: str
    message: str = ""
    priority: NotificationPriority = NotificationPriority.MEDIUM
    source: str = ""
    source_id: str = ""
    action_url: str = ""
    is_read: bool = False
    is_dismissed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["notification_type"] = self.notification_type.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Notification":
        data = data.copy()
        data["notification_type"] = NotificationType(data.get("notification_type", "workspace_update"))
        data["priority"] = NotificationPriority(data.get("priority", "medium"))
        return cls(**data)


class NotificationCenter:
    def __init__(self, storage_dir: str = "collab_data/notifications"):
        self.storage_dir = storage_dir
        self._notifications: dict[str, Notification] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "notifications.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._notifications[k] = Notification.from_dict(v)
                    except Exception as e: logger.warning("Skipping notification %s: %s", k, e)
            except Exception as e: logger.error("Failed to load notifications: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._notifications.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save notifications: %s", e)

    def send(self, org_id: str, user_id: str, notification_type: NotificationType, title: str, message: str = "", priority: NotificationPriority = NotificationPriority.MEDIUM, source: str = "", source_id: str = "", action_url: str = "") -> Notification:
        notif = Notification(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, notification_type=notification_type, title=title, message=message, priority=priority, source=source, source_id=source_id, action_url=action_url)
        self._notifications[notif.id] = notif
        self._save()
        return notif

    def get_notification(self, notif_id: str) -> Optional[Notification]: return self._notifications.get(notif_id)

    def mark_read(self, notif_id: str) -> bool:
        notif = self._notifications.get(notif_id)
        if not notif: return False
        notif.is_read = True
        self._save()
        return True

    def mark_all_read(self, user_id: str) -> int:
        count = 0
        for n in self._notifications.values():
            if n.user_id == user_id and not n.is_read:
                n.is_read = True
                count += 1
        if count: self._save()
        return count

    def dismiss(self, notif_id: str) -> bool:
        notif = self._notifications.get(notif_id)
        if not notif: return False
        notif.is_dismissed = True
        self._save()
        return True

    def list_notifications(self, user_id: str, notification_type: Optional[NotificationType] = None, include_read: bool = False, limit: int = 50) -> list[Notification]:
        results = [n for n in self._notifications.values() if n.user_id == user_id]
        if not include_read: results = [n for n in results if not n.is_dismissed]
        if notification_type: results = [n for n in results if n.notification_type == notification_type]
        return sorted(results, key=lambda n: n.created_at, reverse=True)[:limit]

    def get_unread_count(self, user_id: str) -> int:
        return sum(1 for n in self._notifications.values() if n.user_id == user_id and not n.is_read and not n.is_dismissed)

    def broadcast(self, org_id: str, notification_type: NotificationType, title: str, message: str = "", priority: NotificationPriority = NotificationPriority.MEDIUM, user_ids: list = None) -> list[Notification]:
        sent = []
        for uid in (user_ids or []):
            sent.append(self.send(org_id, uid, notification_type, title, message, priority))
        return sent

    def get_telemetry(self) -> dict: return dict(self._telemetry)
