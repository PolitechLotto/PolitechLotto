import uuid
from datetime import UTC, datetime
from typing import Any, Self

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from lotto.connectors.db import (
    Database,
    build_count_games_query,
    build_list_games_query,
)
from lotto.connectors.models import GameStatus

from .conftest import GAME_TYPE_ID, make_game

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
