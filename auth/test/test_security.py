import uuid
from datetime import UTC, datetime

import jwt
import pytest

from auth.connectors.models import UserRole
from auth.handlers.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

from .conftest import PASSWORD, PASSWORD_HASH, TEST_SETTINGS


def test_password_hash_is_salted_and_verifiable() -> None:
    other_hash = hash_password(PASSWORD)

    assert PASSWORD_HASH.startswith("scrypt$")
    assert PASSWORD not in PASSWORD_HASH
    assert other_hash != PASSWORD_HASH
    assert verify_password(PASSWORD, PASSWORD_HASH)
    assert verify_password(PASSWORD, other_hash)


@pytest.mark.parametrize(
    ("password", "password_hash"),
    [
        ("wrong-password", PASSWORD_HASH),
        (PASSWORD, ""),
        (PASSWORD, "bcrypt$1$2$3$4$5"),
        (PASSWORD, "scrypt$x$8$1$AAAA$AAAA"),
        (PASSWORD, "scrypt$16384$8$1$!!!$AAAA"),
    ],
)
def test_verify_password_rejects(password: str, password_hash: str) -> None:
    assert verify_password(password, password_hash) is False


def test_access_token_claims() -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0)

    token = create_access_token(TEST_SETTINGS, user_id, "gracz", UserRole.ADMIN, now)

    claims = jwt.decode(
        token,
        TEST_SETTINGS.jwt_secret,
        algorithms=["HS256"],
        issuer=TEST_SETTINGS.jwt_issuer,
    )
    assert claims["sub"] == str(user_id)
    assert claims["username"] == "gracz"
    assert claims["role"] == "admin"
    assert claims["iat"] == int(now.timestamp())
    assert claims["exp"] == int((now + TEST_SETTINGS.access_token_ttl).timestamp())


def test_access_token_is_signed() -> None:
    token = create_access_token(
        TEST_SETTINGS, uuid.uuid4(), "gracz", UserRole.PLAYER, datetime.now(UTC)
    )

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "another-secret-that-is-long-enough", algorithms=["HS256"])


def test_refresh_tokens_are_random_and_hashed() -> None:
    first, second = generate_refresh_token(), generate_refresh_token()

    assert first != second
    assert len(first) >= 64
    assert hash_refresh_token(first) == hash_refresh_token(first)
    assert len(hash_refresh_token(first)) == 64
