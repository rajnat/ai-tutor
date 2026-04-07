from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import scrypt, sha256
import hmac
import secrets

from app.core.config import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        derived = scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return f"{salt.hex()}:{derived.hex()}"

    def verify_password(self, password: str, stored_hash: str) -> bool:
        salt_hex, digest_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)

    def issue_session_token(self) -> tuple[str, str, datetime]:
        token = secrets.token_urlsafe(32)
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        expires_at = utc_now() + timedelta(days=get_settings().auth_session_days)
        return token, token_hash, expires_at

    def issue_csrf_token(self) -> str:
        return secrets.token_urlsafe(24)

    def hash_token(self, token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()
