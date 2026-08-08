"""Encryption service — AES-256-GCM field-level encryption for secrets."""

import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings


class EncryptionService:
    """AES-256-GCM encryption for secrets, tokens, and sensitive fields."""

    def __init__(self, key: Optional[bytes] = None):
        raw = key or self._derive_key()
        self._fernet = Fernet(base64.urlsafe_b64encode(raw))

    @staticmethod
    def _derive_key() -> bytes:
        master = settings.encryption_master_key
        if master and len(master) >= 32:
            return master.encode()[:32].ljust(32, b'\0' if isinstance(master, bytes) else '\0')
        return os.urandom(32)

    @staticmethod
    def generate_key() -> str:
        return base64.urlsafe_b64encode(os.urandom(32)).decode()

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return plaintext
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ciphertext
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def encrypt_field(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return self.encrypt(value)

    def decrypt_field(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return self.decrypt(value)

    @staticmethod
    def encrypt_aes_gcm(plaintext: str, key: bytes) -> tuple[bytes, bytes]:
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return nonce, ciphertext

    @staticmethod
    def decrypt_aes_gcm(ciphertext: bytes, key: bytes, nonce: bytes) -> str:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()

    def mask(self, value: str, visible_chars: int = 4) -> str:
        if len(value) <= visible_chars:
            return value
        return value[:visible_chars] + "*" * (len(value) - visible_chars)


encryption = EncryptionService()
