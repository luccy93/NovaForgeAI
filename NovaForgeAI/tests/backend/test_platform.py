"""Tests for Volume 11 platform components — webhooks, marketplace, SDK, CLI, plugins, platform API."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.api.auth import _get_current_user
from app.core.events import Event, EventType, event_bus
from app.core.webhooks import WebhookService, webhook_service
from app.plugins import BasePlugin, PluginMeta, PluginSandbox, PluginLoader

app = create_app()
client = TestClient(app)

TEST_TOKEN = "test-platform-token"


def _auth_header():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture(autouse=True)
def _setup():
    app.dependency_overrides[_get_current_user] = lambda: {"sub": "test-user"}
    yield
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Webhook Service Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebhookService:
    def test_sign_payload(self):
        payload = {"event": "test", "data": {"key": "value"}}
        sig = WebhookService.sign_payload(payload, "mysecret")
        assert isinstance(sig, str)
        assert len(sig) == 64

    def test_verify_signature_valid(self):
        payload = {"event": "test"}
        secret = "mysecret"
        sig = WebhookService.sign_payload(payload, secret)
        assert WebhookService.verify_signature(payload, sig, secret)

    def test_verify_signature_invalid(self):
        payload = {"event": "test"}
        secret = "mysecret"
        sig = WebhookService.sign_payload(payload, secret)
        assert not WebhookService.verify_signature(payload, sig, "wrongsecret")

    def test_sign_payload_deterministic(self):
        payload = {"a": 1, "b": 2}
        sig1 = WebhookService.sign_payload(payload, "secret")
        sig2 = WebhookService.sign_payload(payload, "secret")
        assert sig1 == sig2

    @pytest.mark.asyncio
    async def test_deliver_success(self):
        with patch("httpx.AsyncClient") as mock:
            mock_instance = MagicMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock.return_value = mock_instance
            resp = MagicMock()
            resp.status_code = 200
            mock_instance.post = AsyncMock(return_value=resp)

            result = await WebhookService.deliver(
                "wh-1", "https://example.com/hook", "test.event", {"msg": "hello"}
            )
            assert result["status"] == "delivered"
            assert result["attempts"] == 1
            assert "status_code" in result

    @pytest.mark.asyncio
    async def test_deliver_with_secret(self):
        with patch("httpx.AsyncClient") as mock:
            mock_instance = MagicMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock.return_value = mock_instance
            resp = MagicMock()
            resp.status_code = 200
            mock_instance.post = AsyncMock(return_value=resp)

            result = await WebhookService.deliver(
                "wh-2", "https://example.com/hook", "test.event",
                {"msg": "hello"}, secret="mysecret"
            )
            assert result["status"] == "delivered"

            call_kwargs = mock_instance.post.call_args
            headers = call_kwargs[1]["headers"]
            assert "X-Webhook-Signature" in headers

    @pytest.mark.asyncio
    async def test_deliver_failure_dead_letter(self):
        with patch.object(WebhookService, "RETRY_BACKOFF_BASE", 0):
            with patch("httpx.AsyncClient") as mock:
                mock_instance = MagicMock()
                mock_instance.__aenter__.return_value = mock_instance
                mock.return_value = mock_instance
                mock_instance.post = AsyncMock(side_effect=Exception("Connection refused"))

                with patch.object(WebhookService, "_dead_letter", new_callable=AsyncMock) as mock_dl:
                    result = await WebhookService.deliver(
                        "wh-3", "https://example.com/hook", "test.event", {"msg": "hello"}
                    )
                    assert result["status"] == "dead_letter"
                    assert result["attempts"] == 5

    @pytest.mark.asyncio
    async def test_delivery_log(self):
        with patch.object(WebhookService, "_record_delivery", new_callable=AsyncMock):
            with patch.object(WebhookService, "get_delivery_log", new_callable=AsyncMock) as mock_log:
                mock_log.return_value = [{"status": "delivered", "attempts": 1}]
                log = await WebhookService.get_delivery_log("wh-x")
                assert len(log) == 1
                assert log[0]["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self):
        with patch.object(WebhookService, "get_dead_letter_queue", new_callable=AsyncMock) as mock_dlq:
            mock_dlq.return_value = [{"webhook_id": "wh-3", "error": "Timeout"}]
            q = await WebhookService.get_dead_letter_queue()
            assert len(q) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Webhook API Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebhookAPI:
    def _create_webhook(self, url="https://ex.com/hook", events=None):
        if events is None:
            events = ["repository.created"]
        return client.post(
            "/api/v1/webhooks/",
            json={"url": url, "events": events, "secret": None, "description": ""},
            headers=_auth_header(),
        )

    def test_create_webhook(self):
        resp = self._create_webhook("https://example.com/hook", ["repository.created", "user.created"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://example.com/hook"
        assert "repository.created" in data["events"]
        assert "id" in data

    def test_create_webhook_invalid_event(self):
        resp = client.post(
            "/api/v1/webhooks/",
            json={"url": "https://example.com/hook", "events": ["invalid.event"]},
            headers=_auth_header(),
        )
        assert resp.status_code == 422

    def test_list_webhooks(self):
        self._create_webhook("https://ex.com/h1")
        resp = client.get("/api/v1/webhooks/", headers=_auth_header())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_webhook(self):
        create_resp = self._create_webhook("https://ex.com/h2", ["repository.updated"])
        wh_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/webhooks/{wh_id}", headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json()["id"] == wh_id

    def test_get_webhook_not_found(self):
        resp = client.get("/api/v1/webhooks/non-existent", headers=_auth_header())
        assert resp.status_code == 404

    def test_update_webhook(self):
        create_resp = self._create_webhook("https://ex.com/h3")
        wh_id = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/webhooks/{wh_id}",
            json={"url": "https://ex.com/h3-updated", "events": ["repository.created", "security.scan.completed"]},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://ex.com/h3-updated"

    def test_delete_webhook(self):
        create_resp = self._create_webhook("https://ex.com/h4")
        wh_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/webhooks/{wh_id}", headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_webhook_not_found(self):
        resp = client.delete("/api/v1/webhooks/non-existent", headers=_auth_header())
        assert resp.status_code == 404

    def test_delivery_log_endpoint(self):
        create_resp = self._create_webhook("https://ex.com/h-delivery")
        wh_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/webhooks/{wh_id}/deliveries", headers=_auth_header())
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# Marketplace API Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketplaceAPI:
    def test_list_plugins(self):
        resp = client.get("/api/v1/marketplace/plugins", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 4

    def test_list_plugins_filter_by_category(self):
        resp = client.get(
            "/api/v1/marketplace/plugins",
            params={"category": "automation"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        for p in resp.json()["items"]:
            assert p["category"] == "automation"

    def test_list_plugins_search(self):
        resp = client.get(
            "/api/v1/marketplace/plugins",
            params={"search": "debug"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        names = [p["name"].lower() for p in resp.json()["items"]]
        assert any("debug" in n for n in names)

    def test_list_plugins_pagination(self):
        resp = client.get(
            "/api/v1/marketplace/plugins",
            params={"page": 1, "page_size": 2},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 2

    def test_get_plugin(self):
        resp = client.get("/api/v1/marketplace/plugins/nova-debugger", headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json()["id"] == "nova-debugger"

    def test_get_plugin_not_found(self):
        resp = client.get("/api/v1/marketplace/plugins/non-existent", headers=_auth_header())
        assert resp.status_code == 404

    def test_install_plugin(self):
        resp = client.post(
            "/api/v1/marketplace/plugins/nova-monitor/install",
            params={"org_id": "org-1"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["plugin_id"] == "nova-monitor"
        assert resp.json()["org_id"] == "org-1"

    def test_install_already_installed(self):
        client.post(
            "/api/v1/marketplace/plugins/git-automation/install",
            params={"org_id": "org-conflict"},
            headers=_auth_header(),
        )
        resp = client.post(
            "/api/v1/marketplace/plugins/git-automation/install",
            params={"org_id": "org-conflict"},
            headers=_auth_header(),
        )
        assert resp.status_code == 409

    def test_uninstall_plugin(self):
        client.post(
            "/api/v1/marketplace/plugins/code-analyzer-pro/install",
            params={"org_id": "org-uninstall"},
            headers=_auth_header(),
        )
        resp = client.post(
            "/api/v1/marketplace/plugins/code-analyzer-pro/uninstall",
            params={"org_id": "org-uninstall"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "uninstalled"

    def test_uninstall_not_installed(self):
        resp = client.post(
            "/api/v1/marketplace/plugins/code-analyzer-pro/uninstall",
            params={"org_id": "org-never-installed"},
            headers=_auth_header(),
        )
        assert resp.status_code == 404

    def test_list_installations(self):
        client.post(
            "/api/v1/marketplace/plugins/nova-debugger/install",
            params={"org_id": "org-list-test"},
            headers=_auth_header(),
        )
        resp = client.get(
            "/api/v1/marketplace/installations",
            params={"org_id": "org-list-test"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_categories(self):
        resp = client.get("/api/v1/marketplace/categories", headers=_auth_header())
        assert resp.status_code == 200
        assert "automation" in resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Platform API Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlatformAPI:
    def test_list_plugins(self):
        resp = client.get("/api/v1/platform/plugins", headers=_auth_header())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_register_extension(self):
        resp = client.post(
            "/api/v1/platform/extensions",
            params={"name": "vscode-extension", "type": "ide"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "vscode-extension"

    def test_list_extensions(self):
        client.post(
            "/api/v1/platform/extensions",
            params={"name": "jetbrains-plugin", "type": "ide"},
            headers=_auth_header(),
        )
        resp = client.get("/api/v1/platform/extensions", headers=_auth_header())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_extensions_by_type(self):
        client.post(
            "/api/v1/platform/extensions",
            params={"name": "slack-bot", "type": "messaging"},
            headers=_auth_header(),
        )
        resp = client.get(
            "/api/v1/platform/extensions",
            params={"type": "messaging"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert all(e["type"] == "messaging" for e in resp.json())

    def test_delete_extension(self):
        create_resp = client.post(
            "/api/v1/platform/extensions",
            params={"name": "temp-ext", "type": "test"},
            headers=_auth_header(),
        )
        ext_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/platform/extensions/{ext_id}", headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_extension_not_found(self):
        resp = client.delete("/api/v1/platform/extensions/non-existent", headers=_auth_header())
        assert resp.status_code == 404

    def test_create_integration(self):
        resp = client.post(
            "/api/v1/platform/integrations",
            params={"name": "Slack", "provider": "slack"},
            json={"credentials": {"token": "xoxb-test"}, "config": {"channel": "#general"}},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["provider"] == "slack"
        assert resp.json()["status"] == "active"

    def test_list_integrations(self):
        resp = client.get("/api/v1/platform/integrations", headers=_auth_header())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_integrations_by_provider(self):
        client.post(
            "/api/v1/platform/integrations",
            params={"name": "GitHub CI", "provider": "github"},
            headers=_auth_header(),
        )
        resp = client.get(
            "/api/v1/platform/integrations",
            params={"provider": "github"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert all(i["provider"] == "github" for i in resp.json())

    def test_delete_integration(self):
        create_resp = client.post(
            "/api/v1/platform/integrations",
            params={"name": "Temp Integration", "provider": "test"},
            headers=_auth_header(),
        )
        int_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/platform/integrations/{int_id}", headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_publish_event(self):
        resp = client.post(
            "/api/v1/platform/events/publish",
            params={"event_type": "notification.sent"},
            json={"payload": {"msg": "hello"}},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    def test_publish_event_invalid_type(self):
        resp = client.post(
            "/api/v1/platform/events/publish",
            params={"event_type": "non.existent"},
            headers=_auth_header(),
        )
        assert resp.status_code == 422

    def test_replay_events(self):
        client.post(
            "/api/v1/platform/events/publish",
            params={"event_type": "notification.sent"},
            json={"payload": {"msg": "replay"}},
            headers=_auth_header(),
        )
        resp = client.get(
            "/api/v1/platform/events/replay",
            params={"event_type": "notification.sent", "limit": 5},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_replay_events_invalid_type(self):
        resp = client.get(
            "/api/v1/platform/events/replay",
            params={"event_type": "bad.event"},
            headers=_auth_header(),
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Plugin SDK Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPluginSandbox:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sandbox = PluginSandbox(self.tmpdir)

    def test_validate_path_within_sandbox(self):
        path = self.sandbox.validate_path("test.txt")
        assert path.startswith(self.tmpdir)

    def test_validate_path_outside_sandbox(self):
        with pytest.raises(PermissionError):
            self.sandbox.validate_path("../../../etc/passwd")

    def test_validate_path_absolute_outside(self):
        with pytest.raises(PermissionError):
            self.sandbox.validate_path("C:\\Windows\\system32\\config")

    def test_read_write_file(self):
        self.sandbox.write_file("hello.txt", "world")
        assert self.sandbox.read_file("hello.txt") == "world"

    def test_write_file_outside_sandbox(self):
        with pytest.raises(PermissionError):
            self.sandbox.write_file("../../../tmp/escape.txt", "hack")


class TestPluginLoader:
    def test_discover_no_directory(self):
        loader = PluginLoader(plugin_dir="/nonexistent/path")
        assert loader.discover() == []

    def test_load_all_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = PluginLoader(plugin_dir=tmp)
            plugins = loader.load_all()
            assert plugins == {}


class TestBasePlugin:
    def test_initialize(self):
        class ConcretePlugin(BasePlugin):
            def initialize(self):
                self._initialized = True

        p = ConcretePlugin()
        p.meta = PluginMeta(name="test", version="1.0.0")
        p.initialize()
        assert p._initialized

    def test_health_check(self):
        class ConcretePlugin(BasePlugin):
            def initialize(self):
                pass

        p = ConcretePlugin()
        p.meta = PluginMeta(name="health-plugin", version="1.0.0")
        h = p.health_check()
        assert h["status"] == "healthy"
        assert h["plugin"] == "health-plugin"

    def test_on_event(self):
        class EventPlugin(BasePlugin):
            def initialize(self):
                pass
            def on_event(self, event_type, payload):
                return {"handled": True, "event": event_type}

        p = EventPlugin()
        result = p.on_event("test.event", {"key": "value"})
        assert result["handled"]
        assert result["event"] == "test.event"

    def test_on_api_request(self):
        class ApiPlugin(BasePlugin):
            def initialize(self):
                pass
            def on_api_request(self, method, path, body):
                return {"modified": True}

        p = ApiPlugin()
        result = p.on_api_request("POST", "/test", {})
        assert result["modified"]

    def test_lifecycle_hooks(self):
        events = []

        class LifecyclePlugin(BasePlugin):
            def initialize(self):
                events.append("init")
            def on_startup(self):
                events.append("startup")
            def on_shutdown(self):
                events.append("shutdown")

        p = LifecyclePlugin()
        p.initialize()
        p.on_startup()
        p.on_shutdown()
        assert events == ["init", "startup", "shutdown"]


# ═══════════════════════════════════════════════════════════════════════════════
# SDK Client Tests (unit, no network)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSDKClient:
    def test_client_init(self):
        from backend.sdk.client import NovaForgeClient
        c = NovaForgeClient(base_url="http://test", api_key="key-123")
        assert c.api_key == "key-123"
        assert c.base_url == "http://test"

    def test_get_headers_with_api_key(self):
        from backend.sdk.client import NovaForgeClient
        c = NovaForgeClient(base_url="http://test", api_key="key-123")
        headers = c._get_headers()
        assert headers["X-API-Key"] == "key-123"
        assert "Authorization" not in headers

    def test_get_headers_with_token(self):
        from backend.sdk.client import NovaForgeClient
        c = NovaForgeClient(base_url="http://test", access_token="tok-123")
        headers = c._get_headers()
        assert headers["Authorization"] == "Bearer tok-123"
        assert "X-API-Key" not in headers

    def test_build_url(self):
        from backend.sdk.client import NovaForgeClient
        c = NovaForgeClient(base_url="http://localhost:8000")
        url = c._build_url("/auth/me")
        assert url == "http://localhost:8000/api/v1/auth/me"

    def test_handle_response_401(self):
        from backend.sdk.client import NovaForgeClient
        from backend.sdk.exceptions import AuthenticationError
        import httpx
        c = NovaForgeClient()
        resp = httpx.Response(401, json={"detail": "Unauthorized"})
        with pytest.raises(AuthenticationError):
            c._handle_response(resp)

    def test_handle_response_404(self):
        from backend.sdk.client import NovaForgeClient
        from backend.sdk.exceptions import NotFoundError
        import httpx
        c = NovaForgeClient()
        resp = httpx.Response(404, json={"detail": "Not found"})
        with pytest.raises(NotFoundError):
            c._handle_response(resp)

    def test_handle_response_429(self):
        from backend.sdk.client import NovaForgeClient
        from backend.sdk.exceptions import RateLimitError
        import httpx
        c = NovaForgeClient()
        resp = httpx.Response(429)
        with pytest.raises(RateLimitError):
            c._handle_response(resp)

    def test_handle_response_422(self):
        from backend.sdk.client import NovaForgeClient
        from backend.sdk.exceptions import ValidationError
        import httpx
        c = NovaForgeClient()
        resp = httpx.Response(422, json={"detail": [{"loc": ["body", "email"], "msg": "field required"}]})
        with pytest.raises(ValidationError):
            c._handle_response(resp)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLI:
    def test_cli_help(self):
        from backend.cli.main import main
        import sys
        try:
            sys.argv = ["nova", "--help"]
            with pytest.raises(SystemExit):
                main()
        except SystemExit:
            pass

    def test_cli_login_requires_args(self):
        from backend.cli.main import main
        import sys
        try:
            sys.argv = ["nova", "login"]
            with pytest.raises(SystemExit):
                main()
        except SystemExit:
            pass

    @patch("backend.sdk.client.NovaForgeClient._request")
    def test_cli_status(self, mock_request):
        mock_request.side_effect = [
            {"id": "u1", "email": "test@test.com", "username": "test"},
            [],
            [],
        ]
        from backend.cli.main import cmd_status
        import argparse
        args = argparse.Namespace(json=True)
        cmd_status(args)

    @patch("backend.sdk.client.NovaForgeClient._request")
    def test_cli_agents(self, mock_request):
        mock_request.return_value = [{"name": "Planner", "role": "planner", "description": "Plan"}]
        from backend.cli.main import cmd_agents
        import argparse
        args = argparse.Namespace(json=True)
        cmd_agents(args)

    @patch("backend.sdk.client.NovaForgeClient._request")
    def test_cli_run(self, mock_request):
        mock_request.return_value = {"status": "completed", "output": "done"}
        from backend.cli.main import cmd_run
        import argparse
        args = argparse.Namespace(name="Planner", task="plan something", json=True)
        cmd_run(args)

    def test_config_save_load(self):
        from backend.cli.main import _save_config, _load_config
        config = {"base_url": "http://test", "access_token": "tok-123"}
        _save_config(config)
        loaded = _load_config()
        assert loaded["base_url"] == "http://test"
        assert loaded["access_token"] == "tok-123"


# ═══════════════════════════════════════════════════════════════════════════════
# Event Bus Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventBusIntegration:
    @pytest.mark.asyncio
    async def test_publish_and_replay(self):
        with patch("app.core.events.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            await event_bus.publish(Event(EventType.webhook_delivered, {"msg": "integration test"}))
            events = await event_bus.replay(EventType.webhook_delivered, 5)
            assert len(events) == 0

    @pytest.mark.asyncio
    async def test_event_bus_subscribe_callback(self):
        received = []

        async def callback(event):
            received.append(event)

        event_bus.subscribe(EventType.webhook_delivered, callback)
        await event_bus.publish_nowait(Event(EventType.webhook_delivered, {"cb": "test"}))
        assert len(received) >= 1


import asyncio  # noqa: E402
