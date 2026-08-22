"""Notification service — IAM event notifications."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class NotificationService:
    def __init__(self):
        self._notifications: list[dict] = []

    def send(self, org_id: str, user_id: str, notification_type: str, title: str, message: str, severity: str = "info", metadata: Optional[dict] = None) -> dict:
        notif_id = str(uuid.uuid4())
        notification = {"id": notif_id, "organization_id": org_id, "user_id": user_id, "type": notification_type, "title": title, "message": message, "severity": severity, "metadata": metadata or {}, "is_read": False, "created_at": datetime.now(timezone.utc).isoformat()}
        self._notifications.append(notification)
        return notification

    def send_role_changed(self, org_id: str, user_id: str, old_role: str, new_role: str) -> dict:
        return self.send(org_id, user_id, "role_changed", "Role Updated", f"Your role has been changed from '{old_role}' to '{new_role}'.", "info")

    def send_member_added(self, org_id: str, user_id: str, role: str) -> dict:
        return self.send(org_id, user_id, "member_added", "Organization Membership", f"You have been added to the organization with role '{role}'.", "info")

    def send_member_removed(self, org_id: str, user_id: str) -> dict:
        return self.send(org_id, user_id, "member_removed", "Organization Membership", "You have been removed from the organization.", "warning")

    def send_access_denied(self, org_id: str, user_id: str, permission: str, resource: str = "") -> dict:
        msg = f"Access denied for permission '{permission}'."
        if resource:
            msg += f" Resource: {resource}"
        return self.send(org_id, user_id, "access_denied", "Access Denied", msg, "warning")

    def send_break_glass_activated(self, org_id: str, user_id: str, reason: str) -> dict:
        return self.send(org_id, user_id, "break_glass_activated", "Break-Glass Access Activated", f"Emergency access activated. Reason: {reason}. This session will be audited and auto-expire.", "critical")

    def send_quota_exceeded(self, org_id: str, user_id: str, quota_type: str, limit: int) -> dict:
        return self.send(org_id, user_id, "quota_exceeded", "Quota Exceeded", f"Quota '{quota_type}' has exceeded its limit of {limit}.", "warning")

    def send_api_key_expiring(self, org_id: str, user_id: str, key_name: str, days_left: int) -> dict:
        return self.send(org_id, user_id, "api_key_expiring", "API Key Expiring", f"API key '{key_name}' will expire in {days_left} days.", "info")

    def send_access_review_due(self, org_id: str, admin_user_id: str, review_type: str) -> dict:
        return self.send(org_id, admin_user_id, "access_review_due", "Access Review Due", f"A {review_type} access review is due for your organization.", "info")

    def send_privilege_analysis_complete(self, org_id: str, admin_user_id: str, findings_count: int) -> dict:
        return self.send(org_id, admin_user_id, "privilege_analysis_complete", "Privilege Analysis Complete", f"Privilege analysis completed with {findings_count} findings.", "info")

    def list_for_user(self, user_id: str, unread_only: bool = False) -> list[dict]:
        notifs = [n for n in self._notifications if n["user_id"] == user_id]
        if unread_only:
            notifs = [n for n in notifs if not n["is_read"]]
        return notifs

    def list_for_org(self, org_id: str, unread_only: bool = False) -> list[dict]:
        notifs = [n for n in self._notifications if n["organization_id"] == org_id]
        if unread_only:
            notifs = [n for n in notifs if not n["is_read"]]
        return notifs

    def mark_read(self, notification_id: str) -> bool:
        for n in self._notifications:
            if n["id"] == notification_id:
                n["is_read"] = True
                return True
        return False

    def mark_all_read(self, user_id: str) -> int:
        count = 0
        for n in self._notifications:
            if n["user_id"] == user_id and not n["is_read"]:
                n["is_read"] = True
                count += 1
        return count

    def delete(self, notification_id: str) -> bool:
        before = len(self._notifications)
        self._notifications = [n for n in self._notifications if n["id"] != notification_id]
        return len(self._notifications) < before

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        notifs = list(self._notifications)
        if org_id:
            notifs = [n for n in notifs if n["organization_id"] == org_id]
        return {"total": len(notifs), "unread": sum(1 for n in notifs if not n["is_read"])}


notification_service = NotificationService()
