"""Enhanced JWT service — jti claims, token blacklisting, refresh rotation."""

import uuid
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from app.core.config import settings


class JWTService:
    """JWT with jti claims, blacklisting support, and refresh rotation."""

    ACCESS_EXPIRE_MINUTES = settings.access_token_expire_minutes
    REFRESH_EXPIRE_DAYS = 30

    @staticmethod
    def create_access_token(user_id: str) -> tuple[str, int, str]:
        jti = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=JWTService.ACCESS_EXPIRE_MINUTES)
        payload = {
            "sub": user_id,
            "jti": jti,
            "exp": expire,
            "iat": now,
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return token, JWTService.ACCESS_EXPIRE_MINUTES, jti

    @staticmethod
    def create_refresh_token(user_id: str) -> tuple[str, str]:
        jti = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=JWTService.REFRESH_EXPIRE_DAYS)
        payload = {
            "sub": user_id,
            "jti": jti,
            "exp": expire,
            "iat": now,
            "type": "refresh",
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return token, jti

    @staticmethod
    def decode_token(token: str, expected_type: str = "access") -> Optional[dict]:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            if payload.get("type") != expected_type:
                return None
            return payload
        except JWTError:
            return None

    @staticmethod
    def get_token_jti(token: str) -> Optional[str]:
        payload = JWTService.decode_token(token)
        if payload:
            return payload.get("jti")
        return None

    @staticmethod
    def get_user_id(token: str) -> Optional[str]:
        payload = JWTService.decode_token(token)
        if payload:
            return payload.get("sub")
        return None

    @staticmethod
    def is_token_blacklisted(jti: str, redis_client=None) -> bool:
        if redis_client:
            try:
                return redis_client.get(f"blacklist:{jti}") is not None
            except Exception:
                return False
        return False

    @staticmethod
    def blacklist_token(jti: str, redis_client=None, expire_seconds: int = 86400) -> None:
        if redis_client:
            try:
                from app.core.config import settings
                if hasattr(settings, 'redis_url') and settings.redis_url:
                    import redis as redis_mod
                    r = redis_mod.from_url(settings.redis_url)
                    r.setex(f"blacklist:{jti}", expire_seconds, "1")
            except Exception:
                pass

    @staticmethod
    def rotate_refresh_token(old_refresh_token: str) -> Optional[tuple[str, str, str]]:
        payload = JWTService.decode_token(old_refresh_token, expected_type="refresh")
        if not payload:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        new_token, new_jti = JWTService.create_refresh_token(user_id)
        old_jti = payload.get("jti", "")
        return new_token, new_jti, old_jti


jwt_service = JWTService()
