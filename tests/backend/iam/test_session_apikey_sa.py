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
        assert "session_token" in s

    def test_get(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        fetched = sess.get(s["id"])
        assert fetched["user_id"] == "u1"

    def test_validate(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        valid = sess.validate(s["id"])
        assert valid["valid"] is True
        assert valid["session"]["user_id"] == "u1"

    def test_validate_invalid_token(self, sess):
        result = sess.validate("invalid-token")
        assert result["valid"] is False

    def test_refresh(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        refreshed = sess.refresh(s["id"])
        assert refreshed is not None
        assert refreshed["id"] == s["id"]

    def test_revoke(self, sess):
        s = sess.create("u1", "org-1", "127.0.0.1", "Mozilla/5.0")
        assert sess.revoke(s["id"])
        assert sess.validate(s["id"])["valid"] is False

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
        result = aks.create("org-1", "u1", "test-key", ["org:read"])
        assert "key_data" in result
        assert "raw_key" in result

    def test_validate(self, aks):
        result = aks.create("org-1", "u1", "test-key", ["org:read"])
        valid = aks.validate(result["raw_key"])
        assert valid["valid"] is True

    def test_validate_wrong_key(self, aks):
        result = aks.validate("nf_wrongkey")
        assert result["valid"] is False

    def test_list_for_user(self, aks):
        aks.create("org-1", "u1", "key1", ["org:read"])
        aks.create("org-1", "u1", "key2", ["org:read"])
        aks.create("org-1", "u2", "key3", ["org:read"])
        assert len(aks.list_for_user("u1")) == 2

    def test_revoke(self, aks):
        result = aks.create("org-1", "u1", "test-key", ["org:read"])
        assert aks.revoke(result["key_data"]["id"])
        assert aks.validate(result["raw_key"])["valid"] is False

    def test_rotate(self, aks):
        result = aks.create("org-1", "u1", "test-key", ["org:read"])
        rotated = aks.rotate(result["key_data"]["id"])
        assert "raw_key" in rotated
        assert rotated["raw_key"] != result["raw_key"]

    def test_cleanup_expired(self, aks):
        count = aks.cleanup_expired()
        assert count >= 0

    def test_max_per_user(self, aks):
        for i in range(5):
            aks.create("org-1", "u1", f"key{i}", ["org:read"])
        keys = aks.list_for_user("u1")
        assert len(keys) <= 5

    def test_stats(self, aks):
        aks.create("org-1", "u1", "key1", ["org:read"])
        stats = aks.get_stats()
        assert stats["total"] >= 1


class TestServiceAccount:
    def test_create(self, sas):
        result = sas.create("org-1", "bot", scopes=["org:read"])
        assert "sa_data" in result
        assert "client_secret" in result

    def test_validate(self, sas):
        result = sas.create("org-1", "bot", scopes=["org:read"])
        valid = sas.validate(result["sa_data"]["client_id"], result["client_secret"])
        assert valid["valid"] is True

    def test_validate_wrong_secret(self, sas):
        result = sas.create("org-1", "bot", scopes=["org:read"])
        assert sas.validate(result["sa_data"]["client_id"], "wrong-secret")["valid"] is False

    def test_list_for_org(self, sas):
        sas.create("org-1", "a")
        sas.create("org-1", "b")
        sas.create("org-2", "c")
        assert len(sas.list_for_org("org-1")) == 2

    def test_rotate(self, sas):
        result = sas.create("org-1", "bot")
        rotated = sas.rotate(result["sa_data"]["id"])
        assert "client_secret" in rotated

    def test_disable(self, sas):
        result = sas.create("org-1", "bot")
        assert sas.disable(result["sa_data"]["id"])
        assert sas.get(result["sa_data"]["id"])["is_active"] is False

    def test_update_scopes(self, sas):
        result = sas.create("org-1", "bot", scopes=["org:read"])
        updated = sas.update_scopes(result["sa_data"]["id"], ["org:read", "org:write"])
        assert len(updated["scopes"]) == 2

    def test_max_per_org(self, sas):
        for i in range(5):
            sas.create("org-1", f"sa{i}")
        accounts = sas.list_for_org("org-1")
        assert len(accounts) <= 5

    def test_cleanup_expired(self, sas):
        count = sas.cleanup_expired()
        assert count >= 0

    def test_stats(self, sas):
        sas.create("org-1", "bot")
        stats = sas.get_stats("org-1")
        assert stats["total"] >= 1
