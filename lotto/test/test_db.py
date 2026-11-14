import uuid
from datetime import UTC, datetime
from typing import Any, Self

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from lotto.connectors.db import (
    Database,
    NewGame,
    build_count_games_query,
    build_get_game_query,
    build_list_games_query,
)
from lotto.connectors.models import Game, GameStatus, GameType

from .conftest import GAME_TYPE_ID, make_game, make_game_type, make_game_with_type

DATE_FROM = datetime(2026, 11, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 11, 30, tzinfo=UTC)


def compile_query(query: Select[Any]) -> tuple[str, dict[str, Any]]:
    compiled = query.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split()), compiled.params


def test_list_query_without_filters_has_no_where_and_sorts_descending() -> None:
    sql, params = compile_query(build_list_games_query(None, None, None, None, 20, 0))

    assert "WHERE" not in sql
    assert "ORDER BY games.scheduled_at DESC, games.id DESC" in sql
    assert params["param_1"] == 20
    assert params["param_2"] == 0


def test_list_query_for_scheduled_sorts_ascending() -> None:
    sql, params = compile_query(
        build_list_games_query(GameStatus.SCHEDULED, None, None, None, 10, 5)
    )

    assert "games.status = %(status_1)s" in sql
    assert params["status_1"] is GameStatus.SCHEDULED
    assert "ORDER BY games.scheduled_at ASC, games.id ASC" in sql


@pytest.mark.parametrize("status", [GameStatus.FINISHED, GameStatus.CANCELLED])
def test_list_query_for_other_statuses_sorts_descending(status: GameStatus) -> None:
    sql, _ = compile_query(build_list_games_query(status, None, None, None, 10, 0))

    assert "ORDER BY games.scheduled_at DESC, games.id DESC" in sql


def test_list_query_applies_all_filters_and_pagination() -> None:
    sql, params = compile_query(
        build_list_games_query(
            GameStatus.FINISHED, GAME_TYPE_ID, DATE_FROM, DATE_TO, 15, 30
        )
    )

    assert "games.status = %(status_1)s" in sql
    assert "games.game_type_id = %(game_type_id_1)s::UUID" in sql
    assert "games.scheduled_at >= %(scheduled_at_1)s" in sql
    assert "games.scheduled_at <= %(scheduled_at_2)s" in sql
    assert "LIMIT %(param_1)s::INTEGER OFFSET %(param_2)s::INTEGER" in sql
    assert params["game_type_id_1"] == GAME_TYPE_ID
    assert params["scheduled_at_1"] == DATE_FROM
    assert params["scheduled_at_2"] == DATE_TO
    assert params["param_1"] == 15
    assert params["param_2"] == 30


def test_count_query_uses_same_filters_without_pagination() -> None:
    sql, params = compile_query(
        build_count_games_query(GameStatus.CANCELLED, GAME_TYPE_ID, DATE_FROM, None)
    )

    assert sql.startswith("SELECT count(*) AS count_1 FROM games WHERE")
    assert "games.status = %(status_1)s" in sql
    assert "games.game_type_id = %(game_type_id_1)s::UUID" in sql
    assert "games.scheduled_at >= %(scheduled_at_1)s" in sql
    assert "<=" not in sql
    assert "LIMIT" not in sql
    assert "ORDER BY" not in sql
    assert params["status_1"] is GameStatus.CANCELLED


class FakeScalarResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class FakeSession:
    def __init__(self, items: list[Any], total: int | None) -> None:
        self.items = items
        self.total = total
        self.queries: list[Select[Any]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalars(self, query: Select[Any]) -> FakeScalarResult:
        self.queries.append(query)
        return FakeScalarResult(self.items)

    async def scalar(self, query: Select[Any]) -> int | None:
        self.queries.append(query)
        return self.total


@pytest.fixture
def database() -> Database:
    return Database("postgresql+asyncpg://user:pass@localhost:5432/test")


async def test_list_games_returns_items_and_total(database: Database) -> None:
    games = [make_game(), make_game()]
    session = FakeSession(games, total=7)
    database._sessionmaker = lambda: session  # type: ignore[assignment]

    result = await database.list_games(
        GameStatus.SCHEDULED, GAME_TYPE_ID, None, None, 2, 4
    )

    assert result.items == games
    assert result.total == 7
    items_sql, items_params = compile_query(session.queries[0])
    count_sql, _ = compile_query(session.queries[1])
    assert "ORDER BY games.scheduled_at ASC" in items_sql
    assert items_params["param_1"] == 2
    assert items_params["param_2"] == 4
    assert "count(*)" in count_sql


async def test_list_games_total_defaults_to_zero(database: Database) -> None:
    database._sessionmaker = lambda: FakeSession([], total=None)  # type: ignore[assignment]

    result = await database.list_games(None, None, None, None, 20, 0)

    assert result.items == []
    assert result.total == 0


def test_game_status_enum_stores_lowercase_values() -> None:
    from lotto.connectors.models import Game

    enum_type = Game.__table__.c.status.type
    assert list(enum_type.enums) == ["scheduled", "finished", "cancelled"]  # type: ignore[attr-defined]


def test_game_id_is_uuid() -> None:
    assert isinstance(make_game().id, uuid.UUID)


def test_get_game_query_joins_game_type_and_filters_by_id() -> None:
    game_id = uuid.uuid4()

    sql, params = compile_query(build_get_game_query(game_id))

    assert (
        "JOIN game_types AS game_types_1 ON game_types_1.id = games.game_type_id" in sql
    )
    assert "LEFT OUTER JOIN" not in sql
    assert "game_types_1.name" in sql
    assert "game_types_1.number_pool_size" in sql
    assert "game_types_1.number_pick_count" in sql
    assert "WHERE games.id = %(id_2)s::UUID" in sql
    assert params["id_2"] == game_id


class FakeScalarSession:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.queries: list[Select[Any]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, query: Select[Any]) -> Any:
        self.queries.append(query)
        return self.result


async def test_get_game_returns_game(database: Database) -> None:
    game = make_game_with_type()
    session = FakeScalarSession(game)
    database._sessionmaker = lambda: session  # type: ignore[assignment]

    result = await database.get_game(game.id)

    assert result is game
    _, params = compile_query(session.queries[0])
    assert params["id_2"] == game.id


async def test_get_game_returns_none_for_unknown_id(database: Database) -> None:
    database._sessionmaker = lambda: FakeScalarSession(None)  # type: ignore[assignment]

    assert await database.get_game(uuid.uuid4()) is None


class FakeWriteSession:
    def __init__(self, get_result: Any = None) -> None:
        self.get_result = get_result
        self.added: list[Any] = []
        self.committed = False
        self.get_calls: list[tuple[Any, Any]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, model: Any, key: Any) -> Any:
        self.get_calls.append((model, key))
        return self.get_result

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


async def test_get_game_type_reads_by_primary_key(database: Database) -> None:
    game_type = make_game_type()
    session = FakeWriteSession(get_result=game_type)
    database._sessionmaker = lambda: session  # type: ignore[assignment]

    result = await database.get_game_type(GAME_TYPE_ID)

    assert result is game_type
    assert session.get_calls == [(GameType, GAME_TYPE_ID)]


async def test_count_games_of_type_filters_by_game_type(database: Database) -> None:
    session = FakeScalarSession(3)
    database._sessionmaker = lambda: session  # type: ignore[assignment]

    assert await database.count_games_of_type(GAME_TYPE_ID) == 3
    sql, params = compile_query(session.queries[0])
    assert "count(*)" in sql
    assert params["game_type_id_1"] == GAME_TYPE_ID
    assert "status" not in sql


async def test_create_game_inserts_scheduled_one_time_game(database: Database) -> None:
    session = FakeWriteSession()
    database._sessionmaker = lambda: session  # type: ignore[assignment]
    data = NewGame(
        game_type_id=GAME_TYPE_ID,
        name="Lotto #1",
        ticket_price=10,
        jackpot=1000,
        scheduled_at=DATE_TO,
        seed="seed",
        seed_hash="hash",
    )

    game = await database.create_game(data)

    assert session.added == [game]
    assert session.committed
    assert isinstance(game, Game)
    assert game.status is GameStatus.SCHEDULED
    assert game.game_schedule_id is None
    assert game.game_type_id == GAME_TYPE_ID
    assert game.name == "Lotto #1"
    assert game.ticket_price == 10
    assert game.jackpot == 1000
    assert game.scheduled_at == DATE_TO
    assert game.seed == "seed"
    assert game.seed_hash == "hash"
    assert game.winning_numbers is None
