import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from auth.connectors.db import (
    NewRefreshToken,
    NewUser,
    UserConflictError,
    UserListResult,
)
from auth.connectors.models import User, UserRole, UserStatus
from auth.handlers.security import hash_password
from auth.settings import Settings

USER_ID = uuid.UUID("b0000000-0000-0000-0000-000000000001")
ADMIN_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
PASSWORD = "correct-horse"
# Hashing is slow on purpose, so the hash is computed once for all tests.
PASSWORD_HASH = hash_password(PASSWORD)

TEST_SETTINGS = Settings(jwt_secret="test-secret-that-is-long-enough-for-hs256")


def make_user(**overrides: Any) -> User:
    fields: dict[str, Any] = {
        "id": USER_ID,
        "email": "gracz@example.com",
        "username": "gracz",
        "password_hash": PASSWORD_HASH,
        "role": UserRole.PLAYER,
        "created_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        "last_login_at": None,
        "last_seen_at": None,
        "deleted_at": None,
    }
    fields.update(overrides)
    return User(**fields)


@dataclass
class StoredToken:
    user_id: uuid.UUID
    expires_at: datetime
    revoked_at: datetime | None = None


class FakeDatabase:
    """An in-memory stand-in for `auth.connectors.db.Database`."""

    def __init__(self, users: list[User] | None = None) -> None:
        self.users: dict[uuid.UUID, User] = {user.id: user for user in users or []}
        self.tokens: dict[str, StoredToken] = {}
        self.calls: list[tuple[str, Any]] = []
        self.create_conflict = False

    def add_token(
        self,
        token_hash: str,
        user_id: uuid.UUID = USER_ID,
        expires_at: datetime | None = None,
        revoked_at: datetime | None = None,
    ) -> None:
        self.tokens[token_hash] = StoredToken(
            user_id,
            expires_at or datetime.now(UTC) + timedelta(days=1),
            revoked_at,
        )

    def _usable_token(self, token_hash: str, now: datetime) -> StoredToken | None:
        token = self.tokens.get(token_hash)
        if token is None or token.revoked_at is not None or token.expires_at <= now:
            return None
        return token

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        self.calls.append(("get_user", user_id))
        return self.users.get(user_id)

    async def get_users(self, user_ids: Sequence[uuid.UUID]) -> list[User]:
        self.calls.append(("get_users", list(user_ids)))
        return [self.users[i] for i in user_ids if i in self.users]

    async def get_user_by_login(self, login: str) -> User | None:
        self.calls.append(("get_user_by_login", login))
        login = login.lower()
        return next(
            (
                user
                for user in self.users.values()
                if user.deleted_at is None
                and login in (user.email, user.username.lower())
            ),
            None,
        )

    async def find_conflicting_users(self, email: str, username: str) -> list[User]:
        return [
            user
            for user in self.users.values()
            if user.email == email or user.username.lower() == username.lower()
        ]

    async def list_users(
        self, status: UserStatus, online_since: datetime, limit: int, offset: int
    ) -> UserListResult:
        self.calls.append(("list_users", (status, online_since, limit, offset)))
        users = [user for user in self.users.values() if user.deleted_at is None]
        return UserListResult(items=users[offset : offset + limit], total=len(users))

    async def create_user(self, data: NewUser) -> User:
        if self.create_conflict:
            raise UserConflictError
        user = make_user(
            id=uuid.uuid4(),
            email=data.email,
            username=data.username,
            password_hash=data.password_hash,
            role=data.role,
            created_at=datetime.now(UTC),
        )
        self.users[user.id] = user
        return user

    async def touch_last_seen(self, user_id: uuid.UUID, now: datetime) -> None:
        self.calls.append(("touch_last_seen", user_id))
        self.users[user_id].last_seen_at = now

    async def start_session(
        self, user_id: uuid.UUID, token: NewRefreshToken, now: datetime
    ) -> None:
        self.calls.append(("start_session", user_id))
        self.users[user_id].last_login_at = now
        self.users[user_id].last_seen_at = now
        self.tokens[token.token_hash] = StoredToken(user_id, token.expires_at)

    async def rotate_refresh_token(
        self, old_token_hash: str, new_token: NewRefreshToken, now: datetime
    ) -> User | None:
        token = self._usable_token(old_token_hash, now)
        if token is None:
            return None
        user = self.users.get(token.user_id)
        if user is None or user.deleted_at is not None:
            return None
        token.revoked_at = now
        user.last_seen_at = now
        self.tokens[new_token.token_hash] = StoredToken(user.id, new_token.expires_at)
        return user

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> bool:
        token = self._usable_token(token_hash, now)
        if token is None:
            return False
        token.revoked_at = now
        return True

    async def delete_user(
        self, user_id: uuid.UUID, email: str, username: str, now: datetime
    ) -> User | None:
        self.calls.append(("delete_user", user_id))
        user = self.users.get(user_id)
        if user is None or user.deleted_at is not None:
            return None
        user.email, user.username, user.password_hash = email, username, ""
        user.deleted_at = now
        for token in self.tokens.values():
            if token.user_id == user_id and token.revoked_at is None:
                token.revoked_at = now
        return user


class FakeBroker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if self.error is not None:
            raise self.error
        self.published.append((routing_key, payload))


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def fake_broker() -> FakeBroker:
    return FakeBroker()


@pytest.fixture
def settings() -> Settings:
    return TEST_SETTINGS
