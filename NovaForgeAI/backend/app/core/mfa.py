"""MFA/TOTP service — setup, verify, backup codes, trusted devices."""

import os
import hashlib
import secrets
import hmac
from typing import Optional
from datetime import datetime, timezone


class MFAService:
    """Multi-factor authentication using TOTP."""

    ISSUER = "NovaForge AI"

    @staticmethod
    def generate_totp_secret() -> str:
        return base32_encode(os.urandom(20))

    @staticmethod
    def get_totp_uri(secret: str, email: str) -> str:
        return f"otpauth://totp/{MFAService.ISSUER}:{email}?secret={secret}&issuer={MFAService.ISSUER}&algorithm=SHA1&digits=6&period=30"

    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        try:
            import pyotp
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=1)
        except ImportError:
            return _verify_totp_fallback(secret, code)

    @staticmethod
    def generate_backup_codes(count: int = 10) -> list[dict]:
        codes = []
        for _ in range(count):
            code = secrets.token_hex(5).upper()
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            codes.append({"plain": code, "hash": code_hash, "used": False})
        return codes

    @staticmethod
    def verify_backup_code(code: str, stored_codes: list[dict]) -> Optional[int]:
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        for i, sc in enumerate(stored_codes):
            if not sc.get("used") and hmac.compare_digest(sc.get("hash", ""), code_hash):
                return i
        return None

    @staticmethod
    def generate_recovery_code() -> str:
        return "-".join(secrets.token_hex(3) for _ in range(4)).upper()


def base32_encode(data: bytes) -> str:
    import base64
    return base64.b32encode(data).decode().rstrip("=")


def _verify_totp_fallback(secret: str, code: str) -> bool:
    try:
        import struct
        import time as time_mod
        intervals_no = int(time_mod.time()) // 30
        for offset in (-1, 0, 1):
            counter = struct.pack(">Q", intervals_no + offset)
            h = hmac.new(base32_decode(secret), counter, hashlib.sha1).digest()
            start = h[-1] & 0x0F
            otp = (struct.unpack(">I", h[start:start+4])[0] & 0x7FFFFFFF) % 1000000
            if f"{otp:06d}" == code:
                return True
        return False
    except Exception:
        return False


def base32_decode(s: str) -> bytes:
    import base64
    padding = 8 - (len(s) % 8)
    if padding != 8:
        s += "=" * padding
    return base64.b32decode(s)
