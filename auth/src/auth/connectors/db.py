import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    ColumnElement,
    Select,
    Update,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .models import RefreshToken, User, UserRole, UserStatus


class UserConflictError(Exception):
    """A user with the same email or username already exists."""


@dataclass(frozen=True)
class UserListResult:
    items: list[User]
    total: int


@dataclass(frozen=True)
class NewUser:
    email: str
    username: str
    password_hash: str
    role: UserRole = UserRole.PLAYER


@dataclass(frozen=True)
class NewRefreshToken:
    token_hash: str
    expires_at: datetime


def build_get_user_by_login_query(login: str) -> Select[User]:
    """An active (not deleted) user whose email or username matches `login`."""
    login = login.lower()
    return select(User).where(
        or_(User.email == login, func.lower(User.username) == login),
        User.deleted_at.is_(None),
    )


def build_find_conflicting_users_query(email: str, username: str) -> Select[User]:
    return select(User).where(
        or_(
            User.email == email.lower(),
            func.lower(User.username) == username.lower(),
        )
    )


def build_get_users_query(user_ids: Sequence[uuid.UUID]) -> Select[User]:
    return select(User).where(User.id.in_(user_ids)).order_by(User.username)


def _users_filters(
    status: UserStatus, online_since: datetime
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
    if status is UserStatus.ONLINE:
        filters.append(User.last_seen_at >= online_since)
    elif status is UserStatus.OFFLINE:
        filters.append(
            or_(User.last_seen_at.is_(None), User.last_seen_at < online_since)
        )
    return filters


def build_list_users_query(
    status: UserStatus, online_since: datetime, limit: int, offset: int
) -> Select[User]:
    return (
        select(User)
        .where(*_users_filters(status, online_since))
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
        .offset(offset)
    )


def build_count_users_query(status: UserStatus, online_since: datetime) -> Select[int]:
    return (
        select(func.count())
        .select_from(User)
        .where(*_users_filters(status, online_since))
    )


def build_revoke_refresh_token_query(token_hash: str, now: datetime) -> Update:
    """Revokes a usable refresh token and returns its owner's ID.

    Returns no row when the token does not exist, is already revoked or expired, so a
    token can be used only once, even by concurrent requests.
    """
    return (
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken.user_id)
    )


def build_revoke_user_refresh_tokens_query(user_id: uuid.UUID, now: datetime) -> Update:
    return (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def build_touch_last_seen_query(user_id: uuid.UUID, now: datetime) -> Update:
    return update(User).where(User.id == user_id).values(last_seen_at=now)


class Database:
    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def close(self) -> None:
        await self._engine.dispose()

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        async with self._sessionmaker() as session:
            return await session.get(User, user_id)

    async def get_users(self, user_ids: Sequence[uuid.UUID]) -> list[User]:
        async with self._sessionmaker() as session:
            return list((await session.scalars(build_get_users_query(user_ids))).all())

    async def get_user_by_login(self, login: str) -> User | None:
        async with self._sessionmaker() as session:
            return await session.scalar(build_get_user_by_login_query(login))

    async def find_conflicting_users(self, email: str, username: str) -> list[User]:
        query = build_find_conflicting_users_query(email, username)
        async with self._sessionmaker() as session:
            return list((await session.scalars(query)).all())

    async def list_users(
        self, status: UserStatus, online_since: datetime, limit: int, offset: int
    ) -> UserListResult:
        items_query = build_list_users_query(status, online_since, limit, offset)
        count_query = build_count_users_query(status, online_since)
        async with self._sessionmaker() as session:
            items = list((await session.scalars(items_query)).all())
            total = await session.scalar(count_query) or 0
        return UserListResult(items=items, total=total)

    async def create_user(self, data: NewUser) -> User:
        user = User(
            email=data.email,
            username=data.username,
            password_hash=data.password_hash,
            role=data.role,
        )
        async with self._sessionmaker() as session:
            session.add(user)
            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                raise UserConflictError from e
        return user

    async def touch_last_seen(self, user_id: uuid.UUID, now: datetime) -> None:
        async with self._sessionmaker() as session:
            await session.execute(build_touch_last_seen_query(user_id, now))
            await session.commit()

    async def start_session(
        self, user_id: uuid.UUID, token: NewRefreshToken, now: datetime
    ) -> None:
        """Records a login and stores its refresh token, in one transaction."""
        async with self._sessionmaker() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_login_at=now, last_seen_at=now)
            )
            session.add(
                RefreshToken(
                    user_id=user_id,
                    token_hash=token.token_hash,
                    expires_at=token.expires_at,
                )
            )
            await session.commit()

    async def rotate_refresh_token(
        self, old_token_hash: str, new_token: NewRefreshToken, now: datetime
    ) -> User | None:
        """Revokes a refresh token and stores its replacement, in one transaction.

        Returns the token's owner, or `None` (with nothing changed) when the old token
        is not usable or its owner was deleted.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                build_revoke_refresh_token_query(old_token_hash, now)
            )
            user_id = result.scalar_one_or_none()
            user = await session.get(User, user_id) if user_id is not None else None
            if user is None or user.deleted_at is not None:
                await session.rollback()
                return None
            user.last_seen_at = now
            session.add(
                RefreshToken(
                    user_id=user.id,
                    token_hash=new_token.token_hash,
                    expires_at=new_token.expires_at,
                )
            )
            await session.commit()
            return user

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> bool:
        async with self._sessionmaker() as session:
            result = await session.execute(
                build_revoke_refresh_token_query(token_hash, now)
            )
            revoked = result.scalar_one_or_none() is not None
            await session.commit()
            return revoked

    async def delete_user(
        self, user_id: uuid.UUID, email: str, username: str, now: datetime
    ) -> User | None:
        """Soft-deletes a user: replaces their personal data, removes the password and
        revokes all their refresh tokens. Returns `None` if there was no such user."""
        async with self._sessionmaker() as session:
            user = await session.get(User, user_id)
            if user is None or user.deleted_at is not None:
                return None
            user.email = email
            user.username = username
            user.password_hash = ""
            user.deleted_at = now
            await session.execute(build_revoke_user_refresh_tokens_query(user_id, now))
            await session.commit()
            return user
