import uuid
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

import pytest

from auth.connectors.broker import MessageBroker
from auth.connectors.db import Database
from auth.connectors.models import UserStatus
from auth.handlers import handlers_v1
from auth.handlers.handlers_v1 import (
    USER_CREATED_EVENT,
    USER_DELETED_EVENT,
    CannotDeleteSelfError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenIn,
    TokenCreate,
    UserCreate,
    UserNotFoundError,
    UserTakenError,
    batch_get_users_handler,
    delete_user_handler,
    get_current_user_handler,
    get_user_handler,
    list_users_handler,
    login_handler,
    refresh_token_handler,
    register_user_handler,
    revoke_token_handler,
)
from auth.handlers.security import hash_refresh_token, verify_password
from auth.settings import Settings

from .conftest import ADMIN_ID, PASSWORD, USER_ID, FakeBroker, FakeDatabase, make_user


def db(fake: FakeDatabase) -> Database:
    return cast(Database, fake)


def broker(fake: FakeBroker) -> MessageBroker:
    return cast(MessageBroker, fake)


async def test_register_hashes_password_and_publishes_event(
    fake_db: FakeDatabase, fake_broker: FakeBroker, settings: Settings
) -> None:
    user = await register_user_handler(
        db(fake_db),
        broker(fake_broker),
        settings,
        UserCreate(email="Nowy@Example.com", username="nowy", password=PASSWORD),
    )

    stored = fake_db.users[user.id]
    assert stored.password_hash != PASSWORD
    assert verify_password(PASSWORD, stored.password_hash)
    [(event, payload)] = fake_broker.published
    assert event == USER_CREATED_EVENT
    assert payload["user_id"] == str(user.id)
    assert payload["email"] == "nowy@example.com"
    assert payload["role"] == "player"


async def test_register_maps_insert_conflict_to_user_taken(
    fake_db: FakeDatabase, fake_broker: FakeBroker, settings: Settings
) -> None:
    fake_db.create_conflict = True

    with pytest.raises(UserTakenError):
        await register_user_handler(
            db(fake_db),
            broker(fake_broker),
            settings,
            UserCreate(email="a@b.pl", username="nowy", password=PASSWORD),
        )
    assert fake_broker.published == []


async def test_register_succeeds_when_broker_fails(
    fake_db: FakeDatabase, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    failing = FakeBroker(error=ConnectionError("down"))

    user = await register_user_handler(
        db(fake_db),
        broker(failing),
        settings,
        UserCreate(email="a@b.pl", username="nowy", password=PASSWORD),
    )

    assert user.id in fake_db.users
    assert f"Failed to publish {USER_CREATED_EVENT}" in caplog.text


async def test_login_checks_a_dummy_hash_for_unknown_users(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    with (
        patch.object(
            handlers_v1, "verify_password", wraps=handlers_v1.verify_password
        ) as verify,
        pytest.raises(InvalidCredentialsError),
    ):
        await login_handler(
            db(fake_db), settings, TokenCreate(login="nobody", password=PASSWORD)
        )

    verify.assert_called_once_with(PASSWORD, handlers_v1.DUMMY_PASSWORD_HASH)


async def test_login_rejects_deleted_user_password(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    fake_db.users[USER_ID] = make_user(password_hash="")

    with pytest.raises(InvalidCredentialsError):
        await login_handler(
            db(fake_db), settings, TokenCreate(login="gracz", password=PASSWORD)
        )


async def test_login_strips_login(fake_db: FakeDatabase, settings: Settings) -> None:
    fake_db.users[USER_ID] = make_user()

    await login_handler(
        db(fake_db), settings, TokenCreate(login="  gracz ", password=PASSWORD)
    )

    assert ("get_user_by_login", "gracz") in fake_db.calls


async def test_refresh_rejects_token_of_deleted_user(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    fake_db.users[USER_ID] = make_user(deleted_at=datetime.now(UTC))
    fake_db.add_token(hash_refresh_token("token"))

    with pytest.raises(InvalidRefreshTokenError):
        await refresh_token_handler(
            db(fake_db), settings, RefreshTokenIn(refresh_token="token")
        )


async def test_refresh_rejects_revoked_token(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    fake_db.users[USER_ID] = make_user()
    fake_db.add_token(hash_refresh_token("token"), revoked_at=datetime.now(UTC))

    with pytest.raises(InvalidRefreshTokenError):
        await refresh_token_handler(
            db(fake_db), settings, RefreshTokenIn(refresh_token="token")
        )


async def test_revoke_is_idempotent(fake_db: FakeDatabase) -> None:
    fake_db.add_token(hash_refresh_token("token"))

    await revoke_token_handler(db(fake_db), RefreshTokenIn(refresh_token="token"))
    await revoke_token_handler(db(fake_db), RefreshTokenIn(refresh_token="token"))

    assert fake_db.tokens[hash_refresh_token("token")].revoked_at is not None


async def test_current_user_not_found(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    with pytest.raises(UserNotFoundError):
        await get_current_user_handler(db(fake_db), settings, USER_ID)


@pytest.mark.parametrize(
    ("last_seen_ago", "expected"),
    [
        (None, False),
        (timedelta(minutes=1), True),
        (timedelta(minutes=5, seconds=1), False),
    ],
)
async def test_is_online_depends_on_last_seen(
    fake_db: FakeDatabase,
    settings: Settings,
    last_seen_ago: timedelta | None,
    expected: bool,
) -> None:
    last_seen_at = None if last_seen_ago is None else datetime.now(UTC) - last_seen_ago
    fake_db.users[USER_ID] = make_user(last_seen_at=last_seen_at)

    user = await get_user_handler(db(fake_db), settings, USER_ID)

    assert user.is_online is expected


async def test_deleted_user_is_never_online(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    now = datetime.now(UTC)
    fake_db.users[USER_ID] = make_user(last_seen_at=now, deleted_at=now)

    user = await get_user_handler(db(fake_db), settings, USER_ID)

    assert user.is_online is False
    assert user.deleted_at == now


async def test_list_users_passes_online_threshold(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    before = datetime.now(UTC)

    page = await list_users_handler(db(fake_db), settings, UserStatus.ONLINE, 10, 20)

    [(_, (status, online_since, limit, offset))] = fake_db.calls
    assert status is UserStatus.ONLINE
    assert before - settings.online_window <= online_since
    assert online_since <= datetime.now(UTC) - settings.online_window
    assert (limit, offset) == (10, 20)
    assert (page.limit, page.offset, page.total) == (10, 20, 0)


async def test_batch_get_deduplicates_ids(
    fake_db: FakeDatabase, settings: Settings
) -> None:
    other = uuid.uuid4()

    await batch_get_users_handler(db(fake_db), settings, [USER_ID, other, USER_ID])

    assert fake_db.calls == [("get_users", [USER_ID, other])]


async def test_delete_user_frees_email_and_username(
    fake_db: FakeDatabase, fake_broker: FakeBroker
) -> None:
    fake_db.users[USER_ID] = make_user()

    await delete_user_handler(db(fake_db), broker(fake_broker), USER_ID, ADMIN_ID)

    user = fake_db.users[USER_ID]
    assert user.email == f"deleted-{USER_ID.hex}@deleted.invalid"
    assert user.username == f"deleted_{USER_ID.hex[:24]}"
    assert len(user.username) <= 32
    [(event, payload)] = fake_broker.published
    assert event == USER_DELETED_EVENT
    assert payload["user_id"] == str(USER_ID)
    assert payload["deleted_by"] == str(ADMIN_ID)


async def test_delete_self_is_rejected_before_touching_database(
    fake_db: FakeDatabase, fake_broker: FakeBroker
) -> None:
    with pytest.raises(CannotDeleteSelfError):
        await delete_user_handler(db(fake_db), broker(fake_broker), ADMIN_ID, ADMIN_ID)

    assert fake_db.calls == []
