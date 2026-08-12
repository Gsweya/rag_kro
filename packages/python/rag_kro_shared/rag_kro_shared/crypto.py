"""Session-credential encryption at rest (Fernet)."""
import base64
import hashlib

from cryptography.fernet import Fernet

from .config import get_settings


def _key() -> bytes:
    """Derive a stable 32-byte Fernet key from FERENCE_SECRET_KEY.

    If a full Fernet key is provided, use it directly.
    """
    secret = get_settings().fernet_secret_key
    if not secret:
        return base64.urlsafe_b64encode(hashlib.sha256(b"rag_kro_dev_only").digest())
    # full 44-char Fernet key given
    try:
        Fernet(secret.encode())
        return secret.encode()
    except Exception:
        return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


class Crypto:
    def __init__(self) -> None:
        self._fernet = Fernet(_key())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()


_crypto: Crypto | None = None


def get_crypto() -> Crypto:
    global _crypto
    if _crypto is None:
        _crypto = Crypto()
    return _crypto