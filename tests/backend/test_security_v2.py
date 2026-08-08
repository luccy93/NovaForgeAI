"""Volume 10 tests — encryption, MFA, JWT, threat detection, compliance, security middleware."""

import uuid
import time
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytest


# ─── ENCRYPTION SERVICE ─────────────────────────────────────────────────────

class TestEncryptionService:
    def test_encrypt_decrypt_roundtrip(self):
        from app.core.security import EncryptionService
        svc = EncryptionService(b"01234567890123456789012345678901")
        plain = "sensitive-data-123"
        encrypted = svc.encrypt(plain)
        assert encrypted != plain
        decrypted = svc.decrypt(encrypted)
        assert decrypted == plain

    def test_encrypt_empty_string(self):
        from app.core.security import EncryptionService
        svc = EncryptionService(b"01234567890123456789012345678901")
        assert svc.encrypt("") == ""
        assert svc.decrypt("") == ""

    def test_encrypt_field_none(self):
        from app.core.security import EncryptionService
        svc = EncryptionService(b"01234567890123456789012345678901")
        assert svc.encrypt_field(None) is None
        assert svc.decrypt_field(None) is None

    def test_generate_key(self):
        from app.core.security import EncryptionService
        key = EncryptionService.generate_key()
        assert len(key) > 30

    def test_mask_short_value(self):
        from app.core.security import EncryptionService
        svc = EncryptionService(b"01234567890123456789012345678901")
        assert svc.mask("ab", 4) == "ab"

    def test_mask_long_value(self):
        from app.core.security import EncryptionService
        svc = EncryptionService(b"01234567890123456789012345678901")
        masked = svc.mask("sk-abc123def456", 7)
        assert masked.startswith("sk-abc1")
        assert "*" in masked

    def test_encrypt_deterministic(self):
        from app.core.security import EncryptionService
        svc = EncryptionService(b"01234567890123456789012345678901")
        e1 = svc.encrypt("hello")
        e2 = svc.encrypt("hello")
        assert e1 != e2

    def test_aes_gcm_roundtrip(self):
        from app.core.security import EncryptionService
        key = b"01234567890123456789012345678901"
        nonce, ct = EncryptionService.encrypt_aes_gcm("secret data", key)
        pt = EncryptionService.decrypt_aes_gcm(ct, key, nonce)
        assert pt == "secret data"


# ─── JWT SERVICE ────────────────────────────────────────────────────────────

class TestJWTService:
    def test_create_access_token(self):
        from app.core.jwt_service import JWTService
        token, expire_min, jti = JWTService.create_access_token(str(uuid.uuid4()))
        assert token is not None
        assert expire_min > 0
        assert jti is not None
        assert len(token) > 20

    def test_create_refresh_token(self):
        from app.core.jwt_service import JWTService
        token, jti = JWTService.create_refresh_token(str(uuid.uuid4()))
        assert token is not None
        assert jti is not None

    def test_decode_valid_token(self):
        from app.core.jwt_service import JWTService
        user_id = str(uuid.uuid4())
        token, _, _ = JWTService.create_access_token(user_id)
        payload = JWTService.decode_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        assert "jti" in payload

    def test_decode_invalid_token(self):
        from app.core.jwt_service import JWTService
        assert JWTService.decode_token("invalid.token.here") is None

    def test_decode_wrong_type(self):
        from app.core.jwt_service import JWTService
        token, _ = JWTService.create_refresh_token(str(uuid.uuid4()))
        payload = JWTService.decode_token(token, expected_type="access")
        assert payload is None

    def test_get_token_jti(self):
        from app.core.jwt_service import JWTService
        token, _, jti = JWTService.create_access_token(str(uuid.uuid4()))
        assert JWTService.get_token_jti(token) == jti

    def test_get_user_id(self):
        from app.core.jwt_service import JWTService
        uid = str(uuid.uuid4())
        token, _, _ = JWTService.create_access_token(uid)
        assert JWTService.get_user_id(token) == uid

    def test_rotate_refresh_token(self):
        from app.core.jwt_service import JWTService
        uid = str(uuid.uuid4())
        old_token, _ = JWTService.create_refresh_token(uid)
        rotated = JWTService.rotate_refresh_token(old_token)
        assert rotated is not None
        new_token, new_jti, old_jti = rotated
        assert new_token != old_token
        assert new_jti != old_jti

    def test_rotate_invalid_token(self):
        from app.core.jwt_service import JWTService
        assert JWTService.rotate_refresh_token("bad") is None


# ─── MFA SERVICE ────────────────────────────────────────────────────────────

class TestMFAService:
    def test_generate_totp_secret(self):
        from app.core.mfa import MFAService
        secret = MFAService.generate_totp_secret()
        assert len(secret) >= 16

    def test_get_totp_uri(self):
        from app.core.mfa import MFAService
        uri = MFAService.get_totp_uri("JBSWY3DPEHPK3PXP", "user@example.com")
        assert "otpauth://totp/" in uri
        assert "NovaForge" in uri
        assert "user@example.com" in uri

    def test_generate_backup_codes(self):
        from app.core.mfa import MFAService
        codes = MFAService.generate_backup_codes(5)
        assert len(codes) == 5
        for c in codes:
            assert "plain" in c
            assert "hash" in c
            assert c["used"] is False
            assert len(c["plain"]) == 10

    def test_verify_backup_code_valid(self):
        from app.core.mfa import MFAService
        codes = MFAService.generate_backup_codes(3)
        code = codes[1]["plain"]
        idx = MFAService.verify_backup_code(code, codes)
        assert idx == 1

    def test_verify_backup_code_invalid(self):
        from app.core.mfa import MFAService
        codes = MFAService.generate_backup_codes(3)
        idx = MFAService.verify_backup_code("INVALID", codes)
        assert idx is None

    def test_verify_backup_code_used(self):
        from app.core.mfa import MFAService
        codes = MFAService.generate_backup_codes(3)
        codes[0]["used"] = True
        idx = MFAService.verify_backup_code(codes[0]["plain"], codes)
        assert idx is None

    def test_generate_recovery_code(self):
        from app.core.mfa import MFAService
        code = MFAService.generate_recovery_code()
        assert len(code) >= 10


# ─── THREAT DETECTION ──────────────────────────────────────────────────────

class TestThreatDetector:
    def test_record_auth_failure_triggers_alert(self):
        from app.core.threat_detection import ThreatDetector
        td = ThreatDetector()
        alert = None
        for _ in range(10):
            alert = td.record_event("auth_failure", "192.168.1.1", "user@test.com")
        assert alert is not None
        assert alert["type"] == "brute_force"

    def test_api_key_failure_triggers_alert(self):
        from app.core.threat_detection import ThreatDetector
        td = ThreatDetector()
        alert = None
        for _ in range(5):
            alert = td.record_event("api_key_failure", "10.0.0.1")
        assert alert is not None
        assert alert["type"] == "api_key_abuse"

    def test_is_ip_flagged(self):
        from app.core.threat_detection import ThreatDetector
        td = ThreatDetector()
        for _ in range(10):
            td.record_event("auth_failure", "203.0.113.1")
        assert td.is_ip_flagged("203.0.113.1") is True

    def test_is_ip_not_flagged(self):
        from app.core.threat_detection import ThreatDetector
        td = ThreatDetector()
        assert td.is_ip_flagged("1.2.3.4") is False

    def test_get_recent_alerts(self):
        from app.core.threat_detection import ThreatDetector
        td = ThreatDetector()
        for _ in range(10):
            td.record_event("auth_failure", "198.51.100.1")
        alerts = td.get_recent_alerts()
        assert len(alerts) > 0


# ─── COMPLIANCE SERVICE ────────────────────────────────────────────────────

class TestComplianceService:
    @pytest.mark.asyncio
    async def test_get_retention_policy(self):
        from app.core.compliance import ComplianceService
        policy = await ComplianceService.get_retention_policy()
        assert "audit_logs" in policy
        assert "messages" in policy
        assert policy["audit_logs"] >= 365

    @pytest.mark.asyncio
    async def test_export_user_data(self):
        from app.core.compliance import ComplianceService
        mock_db = AsyncMock()
        result = await ComplianceService.export_user_data(str(uuid.uuid4()), mock_db)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_delete_user_data(self):
        from app.core.compliance import ComplianceService
        mock_db = AsyncMock()
        mock_db.execute.return_value.rowcount = 3
        result = await ComplianceService.delete_user_data(str(uuid.uuid4()), mock_db)
        assert isinstance(result, dict)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_compliance_report(self):
        from app.core.compliance import ComplianceService
        mock_db = AsyncMock()
        mock_db.execute.return_value = AsyncMock(scalar=MagicMock(return_value=5))
        result = await ComplianceService.get_compliance_report(str(uuid.uuid4()), mock_db)
        assert result["organization_id"] is not None
        assert "checks" in result


# ─── SECURITY HEADERS MIDDLEWARE ────────────────────────────────────────────

class TestSecurityHeadersMiddleware:
    @pytest.mark.asyncio
    async def test_security_headers_applied(self):
        from app.core.security_middleware import SecurityHeadersMiddleware
        from starlette.requests import Request
        from starlette.responses import Response

        async def dummy_call(req):
            return Response(content="ok", media_type="text/plain")

        middleware = SecurityHeadersMiddleware(dummy_call)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "server": ("test", 80),
            "client": ("127.0.0.1", 50000),
        }
        request = Request(scope)
        response = await middleware.dispatch(request, dummy_call)
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Strict-Transport-Security" in response.headers
        assert "Content-Security-Policy" in response.headers
        assert "Referrer-Policy" in response.headers
        assert "Permissions-Policy" in response.headers
        assert "Cache-Control" in response.headers


# ─── RATE LIMITER ──────────────────────────────────────────────────────────

class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_check_ip_allows_request(self):
        from app.core.security_middleware import RateLimiter
        rl = RateLimiter()
        allowed = await rl.check_ip("10.0.0.1", max_requests=10, window=60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_check_user_allows_request(self):
        from app.core.security_middleware import RateLimiter
        rl = RateLimiter()
        allowed = await rl.check_user("user-123", max_requests=10, window=60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_auth_rate_limit_blocks_after_limit(self):
        from app.core.security_middleware import RateLimiter
        rl = RateLimiter()
        for _ in range(10):
            await rl.record_auth_failure("10.0.0.2", "test@test.com")
        allowed = await rl.check_auth("10.0.0.2", max_attempts=5, window=300)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_auth_rate_limit_allows_below_limit(self):
        from app.core.security_middleware import RateLimiter
        rl = RateLimiter()
        allowed = await rl.check_auth("10.0.0.3", max_attempts=5, window=300)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_ip_blocks_after_limit(self):
        from app.core.security_middleware import RateLimiter
        rl = RateLimiter()
        for _ in range(5):
            await rl.check_ip("10.0.0.4", max_requests=3, window=60)
        allowed = await rl.check_ip("10.0.0.4", max_requests=3, window=60)
        assert allowed is False


# ─── API ENDPOINT TESTS ─────────────────────────────────────────────────────

class TestMFAEndpoints:
    @pytest.mark.asyncio
    async def test_setup_mfa(self):
        from app.api.auth_v2 import setup_mfa
        user = MagicMock()
        user.email = "test@example.com"
        user.mfa_secret = None
        user.mfa_backup_codes = None
        user.mfa_recovery_code = None
        mock_db = AsyncMock()
        result = await setup_mfa(current_user=user, db=mock_db)
        assert result.secret is not None
        assert "otpauth://" in result.uri
        assert len(result.backup_codes) >= 5
        assert result.recovery_code is not None

    @pytest.mark.asyncio
    async def test_verify_mfa_not_setup(self):
        from app.api.auth_v2 import verify_mfa, MFAVerifyRequest
        user = MagicMock()
        user.mfa_secret = None
        mock_db = AsyncMock()
        with pytest.raises(Exception):
            await verify_mfa(
                request=MFAVerifyRequest(code="123456"),
                current_user=user,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_verify_mfa_wrong_code(self):
        from app.api.auth_v2 import verify_mfa, MFAVerifyRequest
        from app.core.security import encryption
        user = MagicMock()
        user.mfa_secret = encryption.encrypt("JBSWY3DPEHPK3PXP")
        mock_db = AsyncMock()
        with pytest.raises(Exception):
            await verify_mfa(
                request=MFAVerifyRequest(code="000000"),
                current_user=user,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_disable_mfa(self):
        from app.api.auth_v2 import disable_mfa, MFAVerifyRequest
        from app.core.security import encryption
        user = MagicMock()
        user.mfa_secret = encryption.encrypt("JBSWY3DPEHPK3PXP")
        mock_db = AsyncMock()
        with pytest.raises(Exception):
            await disable_mfa(
                request=MFAVerifyRequest(code="000000"),
                current_user=user,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_verify_backup_code_invalid(self):
        from app.api.auth_v2 import verify_backup_code
        user = MagicMock()
        user.mfa_backup_codes = [{"hash": "abc", "used": False}]
        mock_db = AsyncMock()
        with pytest.raises(Exception):
            await verify_backup_code(code="ABCDEF1234", current_user=user, db=mock_db)


class TestPasswordEndpoints:
    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self):
        from app.api.auth_v2 import change_password, PasswordChangeRequest
        from passlib.context import CryptContext
        pwd = CryptContext(schemes=["bcrypt"])
        user = MagicMock()
        user.hashed_password = pwd.hash("oldpass1")
        user.previous_passwords = []
        mock_db = AsyncMock()
        with pytest.raises(Exception):
            await change_password(
                request=PasswordChangeRequest(current_password="wrong", new_password="NewPass123!"),
                current_user=user,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_change_password_success(self):
        from app.api.auth_v2 import change_password, PasswordChangeRequest
        from passlib.context import CryptContext
        pwd = CryptContext(schemes=["bcrypt"])
        user = MagicMock()
        user.hashed_password = pwd.hash("OldPass123!")
        user.previous_passwords = []
        user.password_changed_at = None
        mock_db = AsyncMock()
        result = await change_password(
            request=PasswordChangeRequest(current_password="OldPass123!", new_password="NewPass456!"),
            current_user=user,
            db=mock_db,
        )
        assert result["status"] == "password_updated"

    @pytest.mark.asyncio
    async def test_password_reset_request(self):
        from app.api.auth_v2 import request_password_reset, PasswordResetRequest
        mock_db = AsyncMock()
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
        result = await request_password_reset(
            request=PasswordResetRequest(email="nonexistent@test.com"),
            db=mock_db,
        )
        assert "if_email_exists" in result["status"]

    @pytest.mark.asyncio
    async def test_password_reset_confirm_invalid(self):
        from app.api.auth_v2 import confirm_password_reset, PasswordResetConfirm
        mock_db = AsyncMock()
        mock_db.execute.return_value = AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
        with pytest.raises(Exception):
            await confirm_password_reset(
                request=PasswordResetConfirm(token="invalid", new_password="NewPass123!"),
                db=mock_db,
            )


class TestSessionEndpoints:
    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        from app.api.auth_v2 import list_sessions
        user = MagicMock()
        user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = result_mock
        result = await list_sessions(current_user=user, authorization=None, db=mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_revoke_session_not_found(self):
        from app.api.auth_v2 import revoke_session
        user = MagicMock()
        user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute.return_value = result_mock
        with pytest.raises(Exception):
            await revoke_session(str(uuid.uuid4()), current_user=user, db=mock_db)

    @pytest.mark.asyncio
    async def test_revoke_session_invalid_id(self):
        from app.api.auth_v2 import revoke_session
        user = MagicMock()
        user.id = uuid.uuid4()
        mock_db = AsyncMock()
        with pytest.raises(Exception):
            await revoke_session("not-a-uuid", current_user=user, db=mock_db)


class TestConsentEndpoints:
    @pytest.mark.asyncio
    async def test_accept_terms(self):
        from app.api.auth_v2 import accept_terms
        user = MagicMock()
        user.terms_accepted_at = None
        mock_db = AsyncMock()
        result = await accept_terms(current_user=user, db=mock_db)
        assert result["status"] == "terms_accepted"

    @pytest.mark.asyncio
    async def test_accept_privacy(self):
        from app.api.auth_v2 import accept_privacy
        user = MagicMock()
        user.privacy_accepted_at = None
        mock_db = AsyncMock()
        result = await accept_privacy(current_user=user, db=mock_db)
        assert result["status"] == "privacy_accepted"

    @pytest.mark.asyncio
    async def test_accept_data_processing(self):
        from app.api.auth_v2 import accept_data_processing
        user = MagicMock()
        user.data_processing_consent = False
        mock_db = AsyncMock()
        result = await accept_data_processing(current_user=user, db=mock_db)
        assert result["status"] == "consent_recorded"


class TestDataEndpoints:
    @pytest.mark.asyncio
    async def test_export_data(self):
        from app.api.auth_v2 import export_my_data
        user = MagicMock()
        user.id = uuid.uuid4()
        mock_db = AsyncMock()
        result = await export_my_data(current_user=user, db=mock_db)
        assert "user_id" in result
        assert "data" in result


# ─── MODULE IMPORTS ─────────────────────────────────────────────────────────

class TestModuleImports:
    def test_import_security(self):
        from app.core.security import EncryptionService, encryption
        assert EncryptionService is not None

    def test_import_mfa(self):
        from app.core.mfa import MFAService
        assert MFAService is not None

    def test_import_jwt_service(self):
        from app.core.jwt_service import JWTService, jwt_service
        assert JWTService is not None

    def test_import_security_middleware(self):
        from app.core.security_middleware import SecurityHeadersMiddleware, RateLimitMiddleware, RateLimiter, rate_limiter
        assert SecurityHeadersMiddleware is not None

    def test_import_threat_detection(self):
        from app.core.threat_detection import ThreatDetector, threat_detector
        assert ThreatDetector is not None

    def test_import_compliance(self):
        from app.core.compliance import ComplianceService, compliance_service
        assert ComplianceService is not None

    def test_import_auth_v2_api(self):
        from app.api.auth_v2 import router
        assert router is not None


# ─── PASSWORD VALIDATION ───────────────────────────────────────────────────

class TestPasswordValidation:
    def test_validate_password_strength_min_length(self):
        from app.api.auth_v2 import _validate_password_strength
        with patch("app.core.config.settings.password_min_length", 8):
            with pytest.raises(Exception):
                _validate_password_strength("Ab1!")
            with pytest.raises(Exception):
                _validate_password_strength("short")

    def test_validate_password_strength_uppercase(self):
        from app.api.auth_v2 import _validate_password_strength
        with patch("app.core.config.settings.password_require_uppercase", True):
            with pytest.raises(Exception):
                _validate_password_strength("abcdefgh1!")

    def test_validate_password_strength_lowercase(self):
        from app.api.auth_v2 import _validate_password_strength
        with patch("app.core.config.settings.password_require_lowercase", True):
            with pytest.raises(Exception):
                _validate_password_strength("ABCDEFGH1!")

    def test_validate_password_strength_digit(self):
        from app.api.auth_v2 import _validate_password_strength
        with patch("app.core.config.settings.password_require_digit", True):
            with pytest.raises(Exception):
                _validate_password_strength("Abcdefgh!")

    def test_validate_password_strength_special(self):
        from app.api.auth_v2 import _validate_password_strength
        with patch("app.core.config.settings.password_require_special", True):
            with pytest.raises(Exception):
                _validate_password_strength("Abcdefgh1")

    def test_validate_password_strength_strong(self):
        from app.api.auth_v2 import _validate_password_strength
        _validate_password_strength("StrongP@ss1")  # should not raise
