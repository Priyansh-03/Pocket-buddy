"""Encrypt / decrypt user LLM API keys at rest."""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    key_material = settings.credentials_encryption_key.strip()
    if key_material:
        raw = key_material.encode()
        if len(raw) == 44:
            return Fernet(raw)
        digest = hashlib.sha256(raw).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Could not decrypt stored credential") from e


def mask_key(plain: str | None) -> str | None:
    if not plain or len(plain) < 8:
        return None
    return f"…{plain[-4:]}"
