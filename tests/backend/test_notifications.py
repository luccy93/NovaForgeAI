"""Tests for notification delivery system — service, API, channels, preferences."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch, call
import pytest
from pytest import MonkeyPatch


# ─── HELPERS ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    result_mock.scalars.return_value.all.return_value = []
    db.execute.return_value = result_mock
    return db


@pytest.fixture
def mock_current_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    return user


# ─── NOTIFICATION SERVICE ────────────────────────────────────────────────────

class TestNotificationService:
    @pytest.mark.asyncio
    async def test_send_notification_creates_in_app(self, mock_db):
        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        result = await svc.send_notification(
            user_id=str(uuid.uuid4()),
            title="Test Title",
            body="Test Body",
            notification_type="test_event",
            action_url="https://example.com",
        )
        assert result is not None
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_without_channels_still_creates_in_app(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        result = await svc.send_notification(
            user_id=str(uuid.uuid4()),
            title="No channels",
            body="Body",
            notification_type="test",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_send_notification_with_slack_channel(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        slack_ch = MagicMock()
        slack_ch.channel_type = "slack"
        slack_ch.config = {"webhook_url": "https://hooks.slack.com/test"}
        slack_ch.is_active = True
        mock_db.execute.return_value.scalars.return_value.all.return_value = [slack_ch]

        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        with patch("app.services.notifications.httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__.return_value.post = AsyncMock()
            result = await svc.send_notification(
                user_id=str(uuid.uuid4()),
                title="Slack Test",
                body="Sent via Slack",
                notification_type="deployment_failed",
            )
            assert result is not None
            mock_httpx.return_value.__aenter__.return_value.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_notification_with_discord_channel(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        dc_ch = MagicMock()
        dc_ch.channel_type = "discord"
        dc_ch.config = {"webhook_url": "https://discord.com/api/webhooks/test"}
        dc_ch.is_active = True
        mock_db.execute.return_value.scalars.return_value.all.return_value = [dc_ch]

        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        with patch("app.services.notifications.httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__.return_value.post = AsyncMock()
            result = await svc.send_notification(
                user_id=str(uuid.uuid4()),
                title="Discord Test",
                body="Sent via Discord",
                notification_type="security_alert",
            )
            assert result is not None
            mock_httpx.return_value.__aenter__.return_value.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_notification_with_email_channel(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        email_ch = MagicMock()
        email_ch.channel_type = "email"
        email_ch.config = {"email": "test@example.com"}
        email_ch.is_active = True
        mock_db.execute.return_value.scalars.return_value.all.return_value = [email_ch]

        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        with patch("app.services.notifications.smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = MagicMock()
            with patch("app.core.config.settings.smtp_host", "smtp.example.com"):
                with patch("app.core.config.settings.smtp_from_email", "noreply@novaforge.ai"):
                    result = await svc.send_notification(
                        user_id=str(uuid.uuid4()),
                        title="Email Test",
                        body="Sent via Email",
                        notification_type="deployment_complete",
                    )
                    assert result is not None
                    mock_smtp.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_with_webhook_channel(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(
            return_value={"system_announcement": ["in_app", "webhook"]}
        )
        wh_ch = MagicMock()
        wh_ch.channel_type = "webhook"
        wh_ch.config = {"url": "https://hooks.example.com/notify", "secret": "s3cret"}
        wh_ch.is_active = True
        mock_db.execute.return_value.scalars.return_value.all.return_value = [wh_ch]

        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        with patch("app.services.notifications.httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__.return_value.post = AsyncMock()
            result = await svc.send_notification(
                user_id=str(uuid.uuid4()),
                title="Webhook Test",
                body="Via webhook",
                notification_type="system_announcement",
                action_url="https://app.novaforge.ai/events",
            )
            assert result is not None
            mock_httpx.return_value.__aenter__.return_value.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_gracefully_handles_failure(self, mock_db):
        ch = MagicMock()
        ch.channel_type = "slack"
        ch.config = {"webhook_url": "https://hooks.slack.com/bad"}
        ch.is_active = True

        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        with patch("app.services.notifications.httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network error"))
            try:
                await svc._dispatch(ch, "Fails", "Body", None)
            except Exception:
                pytest.fail("dispatch should not raise")

    @pytest.mark.asyncio
    async def test_email_skipped_when_smtp_not_configured(self, mock_db):
        ch = MagicMock()
        ch.channel_type = "email"
        ch.config = {"email": "test@example.com"}

        from app.services.notifications import NotificationService
        svc = NotificationService(mock_db)
        with patch("app.core.config.settings.smtp_host", None):
            try:
                await svc._send_email(ch, "Title", "Body")
            except Exception:
                pytest.fail("should not raise when smtp unconfigured")


# ─── PREFERENCES ────────────────────────────────────────────────────────────

class TestNotificationPreferences:
    @pytest.mark.asyncio
    async def test_get_preferences_returns_defaults_when_none_saved(self, mock_db):
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
        from app.services.notifications import get_user_preferences, DEFAULT_PREFERENCES
        prefs = await get_user_preferences(mock_db, str(uuid.uuid4()))
        assert prefs == dict(DEFAULT_PREFERENCES)

    @pytest.mark.asyncio
    async def test_get_preferences_returns_saved(self, mock_db):
        saved = {"deployment_complete": ["in_app", "slack"]}
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=saved))
        from app.services.notifications import get_user_preferences
        prefs = await get_user_preferences(mock_db, str(uuid.uuid4()))
        assert prefs == saved

    @pytest.mark.asyncio
    async def test_save_preferences_inserts_new(self, mock_db):
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
        from app.services.notifications import save_user_preferences
        prefs = {"deployment_complete": ["in_app"]}
        await save_user_preferences(mock_db, str(uuid.uuid4()), prefs)
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_save_preferences_updates_existing(self, mock_db):
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=42))
        from app.services.notifications import save_user_preferences
        prefs = {"deployment_complete": ["slack"]}
        await save_user_preferences(mock_db, str(uuid.uuid4()), prefs)
        assert not mock_db.add.called


# ─── API ENDPOINTS ──────────────────────────────────────────────────────────

class TestNotificationsAPI:
    @pytest.mark.asyncio
    async def test_list_notifications_returns_list(self):
        from app.api.notifications import list_notifications
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [MagicMock(
            id=uuid.uuid4(), title="Test", body="Body",
            notification_type="test", is_read=False, read_at=None,
            action_url=None, created_at=datetime.now(timezone.utc),
        )]
        mock_db.execute.return_value = result_mock
        result = await list_notifications(current_user=current_user, db=mock_db, limit=50, offset=0)
        assert len(result) == 1
        assert result[0].title == "Test"

    @pytest.mark.asyncio
    async def test_list_notifications_filters_unread(self):
        from app.api.notifications import list_notifications
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = result_mock
        result = await list_notifications(current_user=current_user, db=mock_db, limit=50, offset=0, unread_only=True)
        assert result == []

    @pytest.mark.asyncio
    async def test_mark_notification_read(self):
        from app.api.notifications import mark_notification_read
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        notif = MagicMock()
        notif.id = uuid.uuid4()
        notif.is_read = False
        notif.read_at = None
        notif.title = "Test"
        notif.body = "Body"
        notif.notification_type = "test"
        notif.action_url = None
        notif.created_at = datetime.now(timezone.utc)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=notif)
        mock_db.execute.return_value = result_mock
        result = await mark_notification_read(str(notif.id), current_user=current_user, db=mock_db)
        assert result.is_read is True

    @pytest.mark.asyncio
    async def test_mark_notification_read_not_found(self):
        from app.api.notifications import mark_notification_read
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(Exception):
            await mark_notification_read(str(uuid.uuid4()), current_user=current_user, db=mock_db)

    @pytest.mark.asyncio
    async def test_unread_count(self):
        from app.api.notifications import unread_count
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar.return_value = 5
        mock_db.execute.return_value = result_mock
        result = await unread_count(current_user=current_user, db=mock_db)
        assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_list_channels(self):
        from app.api.notifications import list_channels
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        ch = MagicMock()
        ch.id = uuid.uuid4()
        ch.channel_type = "slack"
        ch.name = "My Slack"
        ch.is_active = True
        ch.verified_at = None
        ch.created_at = datetime.now(timezone.utc)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [ch]
        mock_db.execute.return_value = result_mock
        result = await list_channels(current_user=current_user, db=mock_db)
        assert len(result) == 1
        assert result[0].channel_type == "slack"

    @pytest.mark.asyncio
    async def test_create_channel(self):
        from app.api.notifications import create_channel
        from app.schemas import NotificationChannelCreate, NotificationChannelType
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        request = NotificationChannelCreate(
            channel_type=NotificationChannelType.slack,
            name="My Slack",
            config={"webhook_url": "https://hooks.slack.com/test"},
        )
        result = await create_channel(request=request, current_user=current_user, db=mock_db)
        assert result.channel_type == "slack"
        assert result.name == "My Slack"
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_create_channel_discord(self):
        from app.api.notifications import create_channel
        from app.schemas import NotificationChannelCreate, NotificationChannelType
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        request = NotificationChannelCreate(
            channel_type=NotificationChannelType.discord,
            name="My Discord",
            config={"webhook_url": "https://discord.com/api/webhooks/test"},
        )
        result = await create_channel(request=request, current_user=current_user, db=mock_db)
        assert result.channel_type == "discord"

    @pytest.mark.asyncio
    async def test_create_channel_email(self):
        from app.api.notifications import create_channel
        from app.schemas import NotificationChannelCreate, NotificationChannelType
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        request = NotificationChannelCreate(
            channel_type=NotificationChannelType.email,
            name="My Email",
            config={"email": "me@example.com"},
        )
        result = await create_channel(request=request, current_user=current_user, db=mock_db)
        assert result.channel_type == "email"

    @pytest.mark.asyncio
    async def test_create_channel_webhook(self):
        from app.api.notifications import create_channel
        from app.schemas import NotificationChannelCreate, NotificationChannelType
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        request = NotificationChannelCreate(
            channel_type=NotificationChannelType.webhook,
            name="Custom Webhook",
            config={"url": "https://hooks.example.com/notify"},
        )
        result = await create_channel(request=request, current_user=current_user, db=mock_db)
        assert result.channel_type == "webhook"

    @pytest.mark.asyncio
    async def test_update_channel(self):
        from app.api.notifications import update_channel
        from app.schemas import NotificationChannelUpdate
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        ch = MagicMock()
        ch.id = uuid.uuid4()
        ch.channel_type = "slack"
        ch.name = "Old"
        ch.config = {}
        ch.is_active = True
        ch.verified_at = None
        ch.created_at = datetime.now(timezone.utc)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=ch)
        mock_db.execute.return_value = result_mock
        request = NotificationChannelUpdate(name="New Name", is_active=False)
        result = await update_channel(str(ch.id), request=request, current_user=current_user, db=mock_db)
        assert result.name == "New Name"
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_delete_channel(self):
        from app.api.notifications import delete_channel
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        ch = MagicMock()
        ch.id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=ch)
        mock_db.execute.return_value = result_mock
        await delete_channel(str(ch.id), current_user=current_user, db=mock_db)
        mock_db.delete.assert_called_once_with(ch)

    @pytest.mark.asyncio
    async def test_delete_channel_not_found(self):
        from app.api.notifications import delete_channel
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute.return_value = result_mock
        with pytest.raises(Exception):
            await delete_channel(str(uuid.uuid4()), current_user=current_user, db=mock_db)

    @pytest.mark.asyncio
    async def test_test_channel_dispatches(self, mock_db):
        from app.api.notifications import test_channel
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        ch = MagicMock()
        ch.id = uuid.uuid4()
        ch.channel_type = "slack"
        ch.config = {"webhook_url": "https://hooks.slack.com/test"}
        ch.is_active = True
        mock_db.execute.return_value.scalar_one_or_none.return_value = ch
        with patch("app.services.notifications.httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__.return_value.post = AsyncMock()
            result = await test_channel(str(ch.id), current_user=current_user, db=mock_db)
            assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_list_preferences(self):
        from app.api.notifications import list_preferences
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
        result = await list_preferences(current_user=current_user, db=mock_db)
        assert len(result.preferences) == len([
            "deployment_complete", "deployment_failed", "security_alert",
            "security_scan_complete", "member_joined", "member_invite",
            "subscription_change", "usage_threshold", "ai_call_complete",
            "pipeline_complete", "agent_error", "repository_imported",
            "system_announcement",
        ])

    @pytest.mark.asyncio
    async def test_update_preferences(self):
        from app.api.notifications import update_preferences
        from app.schemas import NotificationPreferencesOut, NotificationPreferenceItem, NotificationEventType, NotificationChannelType
        current_user = MagicMock()
        current_user.id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
        prefs = NotificationPreferencesOut(preferences=[
            NotificationPreferenceItem(
                event_type=NotificationEventType.deployment_complete,
                channels=[NotificationChannelType.slack],
                enabled=True,
            ),
        ])
        result = await update_preferences(preferences=prefs, current_user=current_user, db=mock_db)
        assert result.preferences[0].event_type == NotificationEventType.deployment_complete
        assert result.preferences[0].channels == [NotificationChannelType.slack]


# ─── MODULE IMPORTS ─────────────────────────────────────────────────────────

class TestModuleImports:
    def test_service_imports(self):
        from app.services.notifications import NotificationService, get_user_preferences, save_user_preferences
        assert callable(NotificationService)
        assert callable(get_user_preferences)
        assert callable(save_user_preferences)

    def test_router_imports(self):
        from app.api.notifications import router
        assert router is not None

    def test_schemas_import(self):
        from app.schemas import (
            NotificationOut, NotificationChannelCreate, NotificationChannelUpdate,
            NotificationChannelOut, NotificationPreferenceItem, NotificationPreferencesOut,
            NotificationEventType, NotificationChannelType,
        )
        assert NotificationEventType.deployment_complete.value == "deployment_complete"
        assert NotificationChannelType.slack.value == "slack"


# ─── DEFAULT PREFERENCES ────────────────────────────────────────────────────

class TestDefaultPreferences:
    def test_all_event_types_have_defaults(self):
        from app.schemas import NotificationEventType
        from app.services.notifications import DEFAULT_PREFERENCES
        for event_type in NotificationEventType:
            assert event_type.value in DEFAULT_PREFERENCES, f"Missing default for {event_type.value}"

    def test_all_defaults_are_valid_channel_types(self):
        from app.schemas import NotificationChannelType
        from app.services.notifications import DEFAULT_PREFERENCES
        valid = {t.value for t in NotificationChannelType}
        for channels in DEFAULT_PREFERENCES.values():
            for ch in channels:
                assert ch in valid, f"Invalid channel type '{ch}' in defaults"

    def test_in_app_in_all_defaults(self):
        from app.services.notifications import DEFAULT_PREFERENCES
        for event_type, channels in DEFAULT_PREFERENCES.items():
            assert "in_app" in channels, f"Missing in_app for {event_type}"
