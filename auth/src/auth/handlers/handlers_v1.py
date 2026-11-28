import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from auth.connectors.broker import MessageBroker
from auth.connectors.db import (
    Database,
    NewRefreshToken,
    NewUser,
    UserConflictError,
)
from auth.connectors.models import User, UserRole, UserStatus
from auth.handlers.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from auth.settings import Settings

logger = logging.getLogger(__name__)

USER_CREATED_EVENT = "user.created"
USER_DELETED_EVENT = "user.deleted"

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
USERNAME_PATTERN = r"^[A-Za-z0-9_]+$"


class UserNotFoundError(Exception):
    pass


class UserTakenError(Exception):
    """The email or username is already used by another account."""


class EmailTakenError(UserTakenError):
    pass


class UsernameTakenError(UserTakenError):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class CannotDeleteSelfError(Exception):
    pass


Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254, pattern=EMAIL_PATTERN),
    AfterValidator(str.lower),
]
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=32, pattern=USERNAME_PATTERN
    ),
]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class UserCreate(BaseModel):
    email: Email
    username: Username
    password: Password


class UserOut(BaseModel):
    id: UUID
    email: str
    username: str
    role: UserRole
    created_at: datetime
    last_login_at: datetime | None
    last_seen_at: datetime | None
    is_online: bool
    deleted_at: datetime | None


class UsersPage(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int


class UsersBatch(BaseModel):
    items: list[UserOut]


class TokenCreate(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or username.")
    password: str = Field(min_length=1, max_length=128)


class RefreshTokenIn(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")
    refresh_token: str
    refresh_expires_in: int = Field(description="Refresh token lifetime in seconds.")


def _now() -> datetime:
    return datetime.now(UTC)


def _to_user_out(user: User, settings: Settings, now: datetime) -> UserOut:
    is_online = (
        user.deleted_at is None
        and user.last_seen_at is not None
        and user.last_seen_at >= now - settings.online_window
    )
    return UserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        last_seen_at=user.last_seen_at,
        is_online=is_online,
        deleted_at=user.deleted_at,
    )


async def _publish(broker: MessageBroker, event: str, payload: dict[str, Any]) -> None:
    try:
        await broker.publish(event, payload)
    except Exception:
        logger.exception("Failed to publish %s: %s", event, payload)


def _new_refresh_token(
    settings: Settings, now: datetime
) -> tuple[str, NewRefreshToken]:
    token = generate_refresh_token()
    return token, NewRefreshToken(
        token_hash=hash_refresh_token(token),
        expires_at=now + settings.refresh_token_ttl,
    )


def _token_out(
    settings: Settings, user: User, refresh_token: str, now: datetime
) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(
            settings, user.id, user.username, user.role, now
        ),
        expires_in=int(settings.access_token_ttl.total_seconds()),
        refresh_token=refresh_token,
        refresh_expires_in=int(settings.refresh_token_ttl.total_seconds()),
    )


async def register_user_handler(
    database: Database, broker: MessageBroker, settings: Settings, data: UserCreate
) -> UserOut:
    for user in await database.find_conflicting_users(data.email, data.username):
        if user.email == data.email:
            raise EmailTakenError("Email is already registered.")
        raise UsernameTakenError("Username is already taken.")

    try:
        user = await database.create_user(
            NewUser(
                email=data.email,
                username=data.username,
                password_hash=hash_password(data.password),
            )
        )
    except UserConflictError as e:
        # Someone registered the same email or username in the meantime.
        raise UserTakenError("Email or username is already taken.") from e

    await _publish(
        broker,
        USER_CREATED_EVENT,
        {
            "user_id": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": str(user.role),
            "created_at": user.created_at.isoformat(),
        },
    )
    return _to_user_out(user, settings, _now())


async def login_handler(
    database: Database, settings: Settings, data: TokenCreate
) -> TokenOut:
    user = await database.get_user_by_login(data.login.strip())
    if user is None:
        verify_password(data.password, DUMMY_PASSWORD_HASH)
        raise InvalidCredentialsError("Invalid login or password.")
    if not verify_password(data.password, user.password_hash):
        raise InvalidCredentialsError("Invalid login or password.")

    now = _now()
    refresh_token, new_token = _new_refresh_token(settings, now)
    await database.start_session(user.id, new_token, now)
    return _token_out(settings, user, refresh_token, now)


async def refresh_token_handler(
    database: Database, settings: Settings, data: RefreshTokenIn
) -> TokenOut:
    now = _now()
    refresh_token, new_token = _new_refresh_token(settings, now)
    user = await database.rotate_refresh_token(
        hash_refresh_token(data.refresh_token), new_token, now
    )
    if user is None:
        raise InvalidRefreshTokenError("Refresh token is invalid or expired.")
    return _token_out(settings, user, refresh_token, now)


async def revoke_token_handler(database: Database, data: RefreshTokenIn) -> None:
    # Like RFC 7009, an unknown or already revoked token is not an error.
    await database.revoke_refresh_token(hash_refresh_token(data.refresh_token), _now())


async def get_current_user_handler(
    database: Database, settings: Settings, user_id: UUID
) -> UserOut:
    user = await database.get_user(user_id)
    if user is None or user.deleted_at is not None:
        raise UserNotFoundError("User not found.")
    now = _now()
    await database.touch_last_seen(user.id, now)
    user.last_seen_at = now
    return _to_user_out(user, settings, now)


async def list_users_handler(
    database: Database,
    settings: Settings,
    status: UserStatus,
    limit: int,
    offset: int,
) -> UsersPage:
    now = _now()
    result = await database.list_users(
        status, now - settings.online_window, limit, offset
    )
    return UsersPage(
        items=[_to_user_out(user, settings, now) for user in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )


async def get_user_handler(
    database: Database, settings: Settings, user_id: UUID
) -> UserOut:
    user = await database.get_user(user_id)
    if user is None:
        raise UserNotFoundError("User not found.")
    return _to_user_out(user, settings, _now())


async def batch_get_users_handler(
    database: Database, settings: Settings, user_ids: Sequence[UUID]
) -> UsersBatch:
    unique_ids = list(dict.fromkeys(user_ids))
    users = await database.get_users(unique_ids)
    now = _now()
    return UsersBatch(items=[_to_user_out(user, settings, now) for user in users])


async def delete_user_handler(
    database: Database, broker: MessageBroker, user_id: UUID, admin_id: UUID
) -> None:
    if user_id == admin_id:
        raise CannotDeleteSelfError("Admins cannot delete their own account.")

    now = _now()
    user = await database.delete_user(
        user_id,
        email=f"deleted-{user_id.hex}@deleted.invalid",
        username=f"deleted_{user_id.hex[:24]}",
        now=now,
    )
    if user is None:
        raise UserNotFoundError("User not found.")

    await _publish(
        broker,
        USER_DELETED_EVENT,
        {
            "user_id": str(user_id),
            "deleted_by": str(admin_id),
            "deleted_at": now.isoformat(),
        },
    )
