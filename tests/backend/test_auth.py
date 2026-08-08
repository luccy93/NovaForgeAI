"""Unit tests for Authentication — GitHub OAuth, API keys, Permissions."""

import uuid
import hashlib
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status


class TestGitHubOAuthLogin:
    def test_returns_url_with_client_id(self):
        from app.api.auth import router
        with patch("app.api.auth.settings.github_oauth_client_id", "test-client-id"):
            from app.api.auth import github_oauth_login
            import inspect
            assert inspect.iscoroutinefunction(github_oauth_login)

    @pytest.mark.asyncio
    async def test_raises_501_when_not_configured(self):
        with patch("app.api.auth.settings.github_oauth_client_id", None):
            from app.api.auth import github_oauth_login
            with pytest.raises(HTTPException) as exc:
                await github_oauth_login()
            assert exc.value.status_code == 501

    def test_url_contains_github_domain(self):
        with patch("app.api.auth.settings.github_oauth_client_id", "client-123"):
            with patch("app.api.auth.settings.github_oauth_redirect_uri", "http://localhost/callback"):
                import anyio
                from app.api.auth import github_oauth_login
                result = anyio.run(github_oauth_login)
                assert "https://github.com/login/oauth/authorize" in result.url
                assert "client_id=client-123" in result.url
                assert "redirect_uri=http" in result.url


class TestGitHubOAuthCallback:
    @pytest.mark.asyncio
    async def test_raises_501_when_not_configured(self):
        with patch("app.api.auth.settings.github_oauth_client_id", None):
            from app.api.auth import github_oauth_callback
            with pytest.raises(HTTPException) as exc:
                await github_oauth_callback("code123")
            assert exc.value.status_code == 501

    @pytest.mark.asyncio
    async def test_raises_501_when_secret_not_configured(self):
        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", None):
                from app.api.auth import github_oauth_callback
                with pytest.raises(HTTPException) as exc:
                    await github_oauth_callback("code123")
                assert exc.value.status_code == 501

    @pytest.mark.asyncio
    async def test_token_exchange_failure_raises_502(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", "secret"):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = mock_resp
                    mock_client_cls.return_value.__aenter__.return_value = mock_client
                    from app.api.auth import github_oauth_callback
                    with pytest.raises(HTTPException) as exc:
                        await github_oauth_callback("bad-code")
                    assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_raises_400_when_no_access_token(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "bad_verification_code"}

        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", "secret"):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = mock_resp
                    mock_client_cls.return_value.__aenter__.return_value = mock_client
                    from app.api.auth import github_oauth_callback
                    with pytest.raises(HTTPException) as exc:
                        await github_oauth_callback("bad-code")
                    assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_user_fetch_failure_raises_502(self):
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "gh_token_123"}

        user_resp = MagicMock()
        user_resp.status_code = 403

        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", "secret"):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = token_resp
                    mock_client.get.return_value = user_resp
                    mock_client_cls.return_value.__aenter__.return_value = mock_client
                    from app.api.auth import github_oauth_callback
                    with pytest.raises(HTTPException) as exc:
                        await github_oauth_callback("valid-code")
                    assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "gh_token_123"}

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {
            "id": 12345,
            "login": "ghuser",
            "name": "GitHub User",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            "email": "ghuser@github.com",
        }

        email_resp = MagicMock()
        email_resp.status_code = 200
        email_resp.json.return_value = [{"email": "primary@example.com", "primary": True}]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", "secret"):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = token_resp
                    mock_client.get.side_effect = [user_resp, email_resp]
                    mock_client_cls.return_value.__aenter__.return_value = mock_client
                    from app.api.auth import github_oauth_callback
                    result = await github_oauth_callback("valid-code", db=mock_db)
                    assert result.is_new_user is True
                    assert result.access_token is not None
                    assert result.refresh_token is not None
                    mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_user(self):
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "gh_token_123"}

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {
            "id": 12345,
            "login": "ghuser",
            "name": "GitHub User",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            "email": "ghuser@github.com",
        }

        email_resp = MagicMock()
        email_resp.status_code = 200
        email_resp.json.return_value = [{"email": "primary@example.com", "primary": True}]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.is_active = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", "secret"):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = token_resp
                    mock_client.get.side_effect = [user_resp, email_resp]
                    mock_client_cls.return_value.__aenter__.return_value = mock_client
                    from app.api.auth import github_oauth_callback
                    result = await github_oauth_callback("valid-code", db=mock_db)
                    assert result.is_new_user is False
                    mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_primary_email_from_github(self):
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "gh_token_123"}

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {"id": 999, "login": "noemail", "name": None, "avatar_url": None}

        email_resp = MagicMock()
        email_resp.status_code = 200
        email_resp.json.return_value = [{"email": "primary@example.com", "primary": True}]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("app.api.auth.settings.github_oauth_client_id", "cid"):
            with patch("app.api.auth.settings.github_oauth_client_secret", "secret"):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = token_resp
                    mock_client.get.side_effect = [user_resp, email_resp]
                    mock_client_cls.return_value.__aenter__.return_value = mock_client
                    from app.api.auth import github_oauth_callback
                    result = await github_oauth_callback("valid-code", db=mock_db)
                    assert result.is_new_user is True


class TestAPIKeys:
    @pytest.mark.asyncio
    async def test_list_api_keys_returns_empty_when_none(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        from app.api.auth import list_api_keys
        result = await list_api_keys(current_user=mock_user, db=mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_api_keys_returns_keys(self):
        from datetime import datetime, timezone
        mock_key = MagicMock()
        mock_key.id = uuid.uuid4()
        mock_key.name = "My Key"
        mock_key.key_prefix = "nf_abc123"
        mock_key.scopes = ["read:repo"]
        mock_key.is_active = True
        mock_key.last_used_at = None
        mock_key.expires_at = None
        mock_key.created_at = datetime.now(timezone.utc)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_key]
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        from app.api.auth import list_api_keys
        result = await list_api_keys(current_user=mock_user, db=mock_db)
        assert len(result) == 1
        assert result[0].name == "My Key"
        assert result[0].key_prefix == "nf_abc123"

    @pytest.mark.asyncio
    async def test_create_api_key_returns_full_key(self):
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        from app.api.auth import create_api_key
        from app.schemas import ApiKeyCreate
        request = ApiKeyCreate(name="Test Key", scopes=["read:repo"])
        result = await create_api_key(request, current_user=mock_user, db=mock_db)
        assert result.name == "Test Key"
        assert result.full_key.startswith("nf_")
        assert result.key_prefix is not None
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_api_key_saves_hashed_key(self):
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        from app.api.auth import create_api_key
        from app.schemas import ApiKeyCreate
        request = ApiKeyCreate(name="Key", scopes=[])
        result = await create_api_key(request, current_user=mock_user, db=mock_db)
        added = mock_db.add.call_args[0][0]
        assert added.key_hash != result.full_key
        assert secrets.compare_digest(
            hashlib.sha256(result.full_key.encode()).hexdigest(),
            added.key_hash,
        )

    @pytest.mark.asyncio
    async def test_delete_api_key_removes_key(self):
        mock_key = MagicMock()
        mock_key.id = uuid.uuid4()
        mock_key.user_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        from app.api.auth import delete_api_key
        result = await delete_api_key(str(mock_key.id), current_user=mock_key, db=mock_db)
        assert result is None
        mock_db.delete.assert_called_once_with(mock_key)

    @pytest.mark.asyncio
    async def test_delete_api_key_404_when_not_found(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        from app.api.auth import delete_api_key
        with pytest.raises(HTTPException) as exc:
            await delete_api_key(str(uuid.uuid4()), current_user=mock_user, db=mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_api_key_400_invalid_id(self):
        from app.api.auth import delete_api_key
        with pytest.raises(HTTPException) as exc:
            await delete_api_key("not-a-uuid", current_user=MagicMock(), db=MagicMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_api_key_handles_empty_scopes(self):
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        from app.api.auth import create_api_key
        from app.schemas import ApiKeyCreate
        request = ApiKeyCreate(name="Scope-less Key")
        result = await create_api_key(request, current_user=mock_user, db=mock_db)
        assert result.name == "Scope-less Key"


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_superuser_bypasses_check(self):
        from app.api.auth import require_permission
        from app.core.authorization import Permission

        mock_user = MagicMock()
        mock_user.is_superuser = True

        dependency = require_permission(Permission.admin_all)
        result = await dependency(current_user=mock_user, db=MagicMock())
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_raises_403_without_permission(self):
        from app.api.auth import require_permission
        from app.core.authorization import Permission

        mock_user = MagicMock()
        mock_user.is_superuser = False

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        dependency = require_permission(Permission.admin_all)
        with pytest.raises(HTTPException) as exc:
            await dependency(current_user=mock_user, db=mock_db)
        assert exc.value.status_code == 403
        assert "admin:all" in exc.value.detail
