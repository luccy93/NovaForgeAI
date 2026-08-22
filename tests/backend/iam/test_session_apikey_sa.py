"""Session, API Key, Service Account service tests (Volume 52)."""
import pytest
from app.iam.session_service import SessionService
from app.iam.api_key_service import APIKeyService
from app.iam.service_account_service import ServiceAccountService


@pytest.fixture()
def sess():
    return SessionService()


@pytest.fixture()
def aks():
    return APIKeyService()


@pytest.fixture()
def sas():
    return ServiceAccountService()


class TestSession:
    def test_create(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        assert s["user_id"] == "u1"
        assert "token" in s

    def test_get(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        fetched = sess.get(s["id"])
        assert fetched["user_id"] == "u1"

    def test_validate(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        valid = sess.validate(s["token"])
        assert valid is not None
        assert valid["user_id"] == "u1"

    def test_validate_invalid_token(self, sess):
        assert sess.validate("invalid-token") is None

    def test_refresh(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        refreshed = sess.refresh(s["token"])
        assert refreshed is not None
        assert refreshed["id"] == s["id"]

    def test_revoke(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        assert sess.revoke(s["token"])
        assert sess.validate(s["token"]) is None

    def test_revoke_all_for_user(self, sess):
        sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        count = sess.revoke_all_for_user("u1")
        assert count == 2

    def test_list_for_user(self, sess):
        sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        sess.create("u2", "org-1", "127.0.0.1", "Mozilla/5.0")
        assert len(sess.list_for_user("u1")) == 2

    def test_cleanup_expired(self, sess):
        count = sess.cleanup_expired()
        assert count >= 0

    def test_touch(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        assert sess.touch(s["id"]) is True

    def test_max_concurrent(self, sess):
        for i in range(5):
            sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        active = sess.list_for_user("u1")
        assert len(active) <= 5

    def test_stats(self, sess):
        sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        stats = sess.get_stats()
        assert stats["total"] >= 1


class TestAPIKey:
    def test_create(self, aks):
        result = aks.create("u1", "org-1", "test-key", ["org:read"])
        assert result["name"] == "test-key"
        assert "key" in result

    def test_validate(self, aks):
        result = aks.create("u1", "org-1", "test-key", ["org:read"])
        valid = aks.validate(result["key"])
        assert valid is not None

    def test_validate_wrong_key(self, aks):
        assert aks.validate("wrong-key") is None

    def test_list_for_user(self, aks):
        aks.create("u1", "org-1", "key1", ["org:read"])
        aks.create("u1", "org-1", "key2", ["org:read"])
        aks.create("u2", "org-1", "key3", ["org:read"])
        assert len(aks.list_for_user("u1")) == 2

    def test_revoke(self, aks):
        result = aks.create("u1", "org-1", "test-key", ["org:read"])
        assert aks.revoke(result["id"])
        assert aks.validate(result["key"]) is None

    def test_rotate(self, aks):
        result = aks.create("u1", "org-1", "test-key", ["org:read"])
        rotated = aks.rotate(result["id"])
        assert rotated["key"] != result["key"]

    def test_cleanup_expired(self, aks):
        count = aks.cleanup_expired()
        assert count >= 0

    def test_max_per_user(self, aks):
        for i in range(5):
            aks.create("u1", "org-1", f"key{i}", ["org:read"])
        keys = aks.list_for_user("u1")
        assert len(keys) <= 5

    def test_stats(self, aks):
        aks.create("u1", "org-1", "key1", ["org:read"])
        stats = aks.get_stats()
        assert stats["total"] >= 1


class TestServiceAccount:
    def test_create(self, sas):
        result = sas.create({"name": "bot", "organization_id": "org-1", "scopes": ["org:read"]})
        assert result["name"] == "bot"
        assert "client_secret" in result

    def test_validate(self, sas):
        result = sas.create({"name": "bot", "organization_id": "org-1", "scopes": ["org:read"]})
        valid = sas.validate(result["client_id"], result["client_secret"])
        assert valid is not None

    def test_validate_wrong_secret(self, sas):
        result = sas.create({"name": "bot", "organization_id": "org-1", "scopes": ["org:read"]})
        assert sas.validate(result["client_id"], "wrong-secret") is None

    def test_list_for_org(self, sas):
        sas.create({"name": "a", "organization_id": "org-1", "scopes": []})
        sas.create({"name": "b", "organization_id": "org-1", "scopes": []})
        sas.create({"name": "c", "organization_id": "org-2", "scopes": []})
        assert len(sas.list_for_org("org-1")) == 2

    def test_rotate(self, sas):
        result = sas.create({"name": "bot", "organization_id": "org-1", "scopes": []})
        rotated = sas.rotate(result["id"])
        assert rotated["client_secret"] != result["client_secret"]

    def test_disable(self, sas):
        result = sas.create({"name": "bot", "organization_id": "org-1", "scopes": []})
        sas.disable(result["id"])
        assert sas.get(result["id"])["status"] == "disabled"

    def test_update_scopes(self, sas):
        result = sas.create({"name": "bot", "organization_id": "org-1", "scopes": ["org:read"]})
        updated = sas.update_scopes(result["id"], ["org:read", "org:write"])
        assert len(updated["scopes"]) == 2

    def test_max_per_org(self, sas):
        for i in range(5):
            sas.create({"name": f"sa{i}", "organization_id": "org-1", "scopes": []})
        accounts = sas.list_for_org("org-1")
        assert len(accounts) <= 5

    def test_cleanup_expired(self, sas):
        count = sas.cleanup_expired()
        assert count >= 0

    def test_stats(self, sas):
        sas.create({"name": "bot", "organization_id": "org-1", "scopes": []})
        stats = sas.get_stats()
        assert stats["total"] >= 1
