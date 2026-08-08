"""Notification delivery service — email, slack, discord, in-app, webhook."""

import smtplib
import json
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.support import Notification, NotificationChannel
from app.models.user import User
from app.schemas import NotificationChannelType, NotificationEventType


DEFAULT_PREFERENCES: dict[str, list[str]] = {
    NotificationEventType.deployment_complete.value: ["in_app", "email"],
    NotificationEventType.deployment_failed.value: ["in_app", "email", "slack"],
    NotificationEventType.security_alert.value: ["in_app", "email", "slack", "discord"],
    NotificationEventType.security_scan_complete.value: ["in_app", "email"],
    NotificationEventType.member_joined.value: ["in_app", "email"],
    NotificationEventType.member_invite.value: ["in_app", "email"],
    NotificationEventType.subscription_change.value: ["in_app", "email"],
    NotificationEventType.usage_threshold.value: ["in_app", "email"],
    NotificationEventType.ai_call_complete.value: ["in_app"],
    NotificationEventType.pipeline_complete.value: ["in_app", "email"],
    NotificationEventType.agent_error.value: ["in_app", "email", "slack"],
    NotificationEventType.repository_imported.value: ["in_app", "email"],
    NotificationEventType.system_announcement.value: ["in_app", "email"],
}


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        notification_type: str = "system",
        org_id: Optional[str] = None,
        action_url: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> Notification:
        in_app = Notification(
            user_id=user_id,
            organization_id=org_id,
            title=title,
            body=body,
            notification_type=notification_type,
            action_url=action_url,
            extra=extra or {},
        )
        self.db.add(in_app)

        channels = await self._get_active_channels(user_id, notification_type)
        for ch in channels:
            await self._dispatch(ch, title, body, action_url)

        return in_app

    async def _get_active_channels(
        self, user_id: str, event_type: str
    ) -> list[NotificationChannel]:
        pref_key = f"notification_preferences:{user_id}"
        result = await self.db.execute(
            select(text("value")).select_from(text("app_settings")).where(
                text("key = :key AND scope = 'user'")
            ).params(key=pref_key)
        )
        row = result.scalar_one_or_none()
        preferences = row or DEFAULT_PREFERENCES

        allowed_types = set(preferences.get(event_type, ["in_app"]))

        result = await self.db.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user_id,
                NotificationChannel.is_active == True,
            )
        )
        user_channels = result.scalars().all()

        active = []
        for ch in user_channels:
            if ch.channel_type in allowed_types:
                active.append(ch)
        if "in_app" in allowed_types:
            pass
        return active

    async def _dispatch(
        self, channel: NotificationChannel, title: str, body: str, action_url: Optional[str]
    ) -> None:
        try:
            if channel.channel_type == "email":
                await self._send_email(channel, title, body)
            elif channel.channel_type == "slack":
                await self._send_slack(channel, title, body, action_url)
            elif channel.channel_type == "discord":
                await self._send_discord(channel, title, body)
            elif channel.channel_type == "webhook":
                await self._send_webhook(channel, title, body, action_url)
        except Exception:
            pass

    async def _send_email(
        self, channel: NotificationChannel, title: str, body: str
    ) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            return
        to_email = channel.config.get("email") or channel.name
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[NovaForge] {title}"
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = to_email
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_user:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password or "")
            server.send_message(msg)

    async def _send_slack(
        self, channel: NotificationChannel, title: str, body: str, action_url: Optional[str]
    ) -> None:
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            return
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        ]
        if action_url:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"<{action_url}|View details>"},
            })
        payload = {"text": title, "blocks": blocks}
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload)

    async def _send_discord(
        self, channel: NotificationChannel, title: str, body: str
    ) -> None:
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            return
        payload = {
            "embeds": [{
                "title": title,
                "description": body,
                "color": 0x00AEEF,
            }]
        }
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload)

    async def _send_webhook(
        self, channel: NotificationChannel, title: str, body: str, action_url: Optional[str]
    ) -> None:
        url = channel.config.get("url")
        if not url:
            return
        secret = channel.config.get("secret")
        payload = {"event": "notification", "title": title, "body": body, "action_url": action_url}
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Webhook-Secret"] = secret
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=headers)


async def get_user_preferences(db: AsyncSession, user_id: str) -> dict:
    pref_key = f"notification_preferences:{user_id}"
    result = await db.execute(
        select(text("value")).select_from(text("app_settings")).where(
            text("key = :key AND scope = 'user'")
        ).params(key=pref_key)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    return dict(DEFAULT_PREFERENCES)


async def save_user_preferences(db: AsyncSession, user_id: str, preferences: dict) -> None:
    pref_key = f"notification_preferences:{user_id}"
    existing = await db.execute(
        select(text("id")).select_from(text("app_settings")).where(
            text("key = :key AND scope = 'user'")
        ).params(key=pref_key)
    )
    row = existing.scalar_one_or_none()
    if row:
        await db.execute(
            text("UPDATE app_settings SET value = :val, updated_at = :now WHERE id = :id"),
            {"val": json.dumps(preferences), "now": datetime.now(timezone.utc), "id": row},
        )
    else:
        from app.models.support import AppSetting
        setting = AppSetting(
            key=pref_key,
            value=preferences,
            scope="user",
        )
        db.add(setting)
