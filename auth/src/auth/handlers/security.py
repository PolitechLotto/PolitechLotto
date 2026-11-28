"""Password hashing and token generation."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

import jwt

from auth.connectors.models import UserRole
from auth.settings import Settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LENGTH = 64
_SCRYPT_PREFIX = "scrypt"


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_SCRYPT_KEY_LENGTH,
        maxmem=128 * n * r * 2,
    )


def hash_password(password: str) -> str:
    """Hashes a password as `scrypt$n$r$p$<salt>$<hash>`."""
    salt = secrets.token_bytes(16)
    key = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return "$".join(
        [
            _SCRYPT_PREFIX,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64encode(salt),
            _b64encode(key),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        prefix, n, r, p, salt, key = password_hash.split("$")
        if prefix != _SCRYPT_PREFIX:
            return False
        expected = base64.b64decode(key)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the user does not exist, so that a login takes the same time
# whether the user exists or not.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_hex(16))


def create_access_token(
    settings: Settings,
    user_id: uuid.UUID,
    username: str,
    role: UserRole,
    now: datetime,
) -> str:
    claims = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "username": username,
        "role": str(role),
        "iat": now,
        "exp": now + settings.access_token_ttl,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Refresh tokens are random, so a plain SHA-256 is enough to store them safely."""
    return hashlib.sha256(token.encode()).hexdigest()
