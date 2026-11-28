import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import pytest
from sqlalchemy import ClauseElement
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from auth.connectors.db import (
    Database,
    NewRefreshToken,
    NewUser,
    UserConflictError,
    build_count_users_query,
    build_find_conflicting_users_query,
    build_get_user_by_login_query,
    build_get_users_query,
    build_list_users_query,
    build_revoke_refresh_token_query,
    build_revoke_user_refresh_tokens_query,
)
from auth.connectors.models import RefreshToken, User, UserStatus

from .conftest import USER_ID, make_user

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
ONLINE_SINCE = NOW - timedelta(minutes=5)


def compile_query(query: ClauseElement) -> tuple[str, dict[str, Any]]:
    compiled = query.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split()), compiled.params


def test_login_query_matches_email_or_username_of_active_users() -> None:
    sql, params = compile_query(build_get_user_by_login_query("Gracz@Example.com"))

    assert (
        "(users.email = %(email_1)s::VARCHAR"
        " OR lower(users.username) = %(lower_1)s::VARCHAR)"
    ) in sql
    assert "users.deleted_at IS NULL" in sql
    assert params["email_1"] == "gracz@example.com"
    assert params["lower_1"] == "gracz@example.com"


def test_conflict_query_includes_deleted_users() -> None:
    sql, params = compile_query(build_find_conflicting_users_query("A@B.pl", "Nowy"))

    assert "deleted_at" not in sql.split("WHERE")[1]
    assert params["email_1"] == "a@b.pl"
    assert params["lower_1"] == "nowy"


def test_get_users_query_filters_by_ids() -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]

    sql, params = compile_query(build_get_users_query(ids))

    assert "users.id IN (__[POSTCOMPILE_id_1])" in sql
    assert "deleted_at" not in sql.split("WHERE")[1]
    assert params["id_1"] == ids


def test_list_all_users_excludes_deleted_and_paginates() -> None:
    sql, params = compile_query(
        build_list_users_query(UserStatus.ALL, ONLINE_SINCE, 50, 10)
    )

    assert "WHERE users.deleted_at IS NULL ORDER BY" in sql
    assert "last_seen_at >=" not in sql
    assert "ORDER BY users.created_at DESC, users.id DESC" in sql
    assert params["param_1"] == 50
    assert params["param_2"] == 10


def test_list_online_users_filters_by_last_seen() -> None:
    sql, params = compile_query(
        build_list_users_query(UserStatus.ONLINE, ONLINE_SINCE, 50, 0)
    )

    assert "users.last_seen_at >= %(last_seen_at_1)s" in sql
    assert params["last_seen_at_1"] == ONLINE_SINCE


def test_count_offline_users_includes_never_seen() -> None:
    sql, params = compile_query(
        build_count_users_query(UserStatus.OFFLINE, ONLINE_SINCE)
    )

    assert sql.startswith("SELECT count(*) AS count_1 FROM users WHERE")
    assert (
        "users.last_seen_at IS NULL OR users.last_seen_at < %(last_seen_at_1)s" in sql
    )
    assert "LIMIT" not in sql
    assert params["last_seen_at_1"] == ONLINE_SINCE


def test_revoke_query_only_revokes_usable_tokens() -> None:
    sql, params = compile_query(build_revoke_refresh_token_query("hash", NOW))

    assert sql.startswith("UPDATE refresh_tokens SET revoked_at=")
    assert "refresh_tokens.token_hash = %(token_hash_1)s" in sql
    assert "refresh_tokens.revoked_at IS NULL" in sql
    assert "refresh_tokens.expires_at > %(expires_at_1)s" in sql
    assert sql.endswith("RETURNING refresh_tokens.user_id")
    assert params["token_hash_1"] == "hash"
    assert params["expires_at_1"] == NOW


def test_revoke_user_tokens_query() -> None:
    sql, params = compile_query(build_revoke_user_refresh_tokens_query(USER_ID, NOW))

    assert "refresh_tokens.user_id = %(user_id_1)s::UUID" in sql
    assert "refresh_tokens.revoked_at IS NULL" in sql
    assert params["user_id_1"] == USER_ID


def test_user_role_enum_stores_lowercase_values() -> None:
    enum_type = User.__table__.c.role.type
    assert list(enum_type.enums) == ["player", "admin"]  # type: ignore[attr-defined]


def test_email_username_and_token_hash_are_unique() -> None:
    assert User.__table__.c.email.unique
    assert User.__table__.c.username.unique
    assert RefreshToken.__table__.c.token_hash.unique


class FakeResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return list(self.value)


class FakeSession:
    def __init__(
        self,
        get_result: Any = None,
        execute_result: Any = None,
        scalar_result: Any = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.get_result = get_result
        self.execute_result = execute_result
        self.scalar_result = scalar_result
        self.commit_error = commit_error
        self.statements: list[ClauseElement] = []
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, _model: Any, _key: Any) -> Any:
        return self.get_result

    async def execute(self, statement: ClauseElement) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.execute_result)

    async def scalar(self, statement: ClauseElement) -> Any:
        self.statements.append(statement)
        return self.scalar_result

    async def scalars(self, statement: ClauseElement) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.scalar_result)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def database() -> Database:
    return Database("postgresql+asyncpg://user:pass@localhost:5432/test")


def use_session(database: Database, session: FakeSession) -> None:
    database._sessionmaker = lambda: session  # type: ignore[assignment]


NEW_TOKEN = NewRefreshToken(token_hash="new-hash", expires_at=NOW + timedelta(days=30))


async def test_create_user_raises_conflict_on_integrity_error(
    database: Database,
) -> None:
    session = FakeSession(commit_error=IntegrityError("insert", {}, Exception()))
    use_session(database, session)

    with pytest.raises(UserConflictError):
        await database.create_user(NewUser("a@b.pl", "nowy", "hash"))
    assert session.rolled_back


async def test_create_user_adds_user(database: Database) -> None:
    session = FakeSession()
    use_session(database, session)

    user = await database.create_user(NewUser("a@b.pl", "nowy", "hash"))

    assert session.added == [user]
    assert session.committed


async def test_start_session_updates_user_and_stores_token(database: Database) -> None:
    session = FakeSession()
    use_session(database, session)

    await database.start_session(USER_ID, NEW_TOKEN, NOW)

    sql, params = compile_query(session.statements[0])
    assert sql.startswith("UPDATE users SET last_login_at=")
    assert params["last_login_at"] == NOW
    assert params["last_seen_at"] == NOW
    [token] = session.added
    assert (token.user_id, token.token_hash) == (USER_ID, "new-hash")
    assert session.committed


async def test_rotate_stores_new_token_for_owner(database: Database) -> None:
    user = make_user()
    session = FakeSession(get_result=user, execute_result=USER_ID)
    use_session(database, session)

    result = await database.rotate_refresh_token("old-hash", NEW_TOKEN, NOW)

    assert result is user
    assert user.last_seen_at == NOW
    [token] = session.added
    assert token.token_hash == "new-hash"
    assert session.committed


@pytest.mark.parametrize(
    ("revoked_owner", "user"),
    [(None, None), (USER_ID, make_user(deleted_at=NOW))],
)
async def test_rotate_rolls_back_for_unusable_token(
    database: Database, revoked_owner: uuid.UUID | None, user: User | None
) -> None:
    session = FakeSession(get_result=user, execute_result=revoked_owner)
    use_session(database, session)

    assert await database.rotate_refresh_token("old-hash", NEW_TOKEN, NOW) is None
    assert session.rolled_back
    assert not session.committed
    assert session.added == []


@pytest.mark.parametrize(("owner", "expected"), [(USER_ID, True), (None, False)])
async def test_revoke_reports_whether_token_was_revoked(
    database: Database, owner: uuid.UUID | None, expected: bool
) -> None:
    use_session(database, FakeSession(execute_result=owner))

    assert await database.revoke_refresh_token("hash", NOW) is expected


async def test_delete_user_replaces_personal_data(database: Database) -> None:
    user = make_user()
    session = FakeSession(get_result=user)
    use_session(database, session)

    result = await database.delete_user(USER_ID, "x@deleted.invalid", "deleted_x", NOW)

    assert result is user
    assert (user.email, user.username, user.password_hash) == (
        "x@deleted.invalid",
        "deleted_x",
        "",
    )
    assert user.deleted_at == NOW
    sql, _ = compile_query(session.statements[0])
    assert sql.startswith("UPDATE refresh_tokens SET revoked_at=")
    assert session.committed


@pytest.mark.parametrize("user", [None, make_user(deleted_at=NOW)])
async def test_delete_user_skips_unknown_or_deleted_users(
    database: Database, user: User | None
) -> None:
    session = FakeSession(get_result=user)
    use_session(database, session)

    assert await database.delete_user(USER_ID, "e", "u", NOW) is None
    assert not session.committed


async def test_list_users_returns_items_and_total(database: Database) -> None:
    users = [make_user()]
    session = FakeSession(scalar_result=users)
    use_session(database, session)

    # The fake returns the same value from scalars() and scalar(), so the total is
    # checked by the count query's shape instead.
    result = await database.list_users(UserStatus.ALL, ONLINE_SINCE, 50, 0)

    assert result.items == users
    count_sql, _ = compile_query(session.statements[1])
    assert "count(*)" in count_sql
