import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus

from .factories import make_game, make_game_type


class FakeSession:
    """Records executed statements and returns canned results: the count first, then the page."""

    def __init__(self, total: int, games: list[Any]) -> None:
        self.statements: list[Any] = []
        self._total = total
        self._games = games

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        if len(self.statements) == 1:
            result.scalar_one.return_value = self._total
        else:
            result.scalars.return_value.all.return_value = self._games
        return result


def compile_sql(statement: Any) -> str:
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    return " ".join(sql.split())


def make_database(session: FakeSession) -> Database:
    return Database(session_factory=lambda: session)  # type: ignore[arg-type,return-value]


DEFAULT_ARGS: dict[str, Any] = {
    "status": None,
    "game_type_id": None,
    "scheduled_from": None,
    "scheduled_to": None,
    "limit": 50,
    "offset": 0,
}


GAME_COLUMNS = (
    "games.id, games.game_type_id, games.game_schedule_id, games.name, "
    "games.ticket_price, games.jackpot, games.status, games.scheduled_at, "
    "games.started_at, games.finished_at, games.seed_hash, games.seed, "
    "games.winning_numbers"
)


async def test_list_games_returns_games_and_total() -> None:
    games = [make_game(), make_game()]
    session = FakeSession(total=7, games=games)

    result_games, total = await make_database(session).list_games(**DEFAULT_ARGS)

    assert (list(result_games), total) == (games, 7)


async def test_list_games_without_filters() -> None:
    session = FakeSession(total=0, games=[])
    expected = [
        "SELECT count(*) AS count_1 FROM games",
        (
            f"SELECT {GAME_COLUMNS} FROM games"
            " ORDER BY games.scheduled_at DESC, games.id DESC LIMIT 50 OFFSET 0"
        ),
    ]

    await make_database(session).list_games(**DEFAULT_ARGS)

    assert [compile_sql(s) for s in session.statements] == expected


async def test_list_games_applies_filters_to_count_and_page() -> None:
    session = FakeSession(total=0, games=[])
    where = (
        "WHERE games.status = 'finished'"
        " AND games.game_type_id = '00000000-0000-0000-0000-000000000001'"
        " AND games.scheduled_at >= '2026-11-01 00:00:00+00:00'"
        " AND games.scheduled_at <= '2026-11-30 00:00:00+00:00'"
    )
    expected = [
        f"SELECT count(*) AS count_1 FROM games {where}",
        (
            f"SELECT {GAME_COLUMNS} FROM games {where}"
            " ORDER BY games.scheduled_at DESC, games.id DESC LIMIT 20 OFFSET 40"
        ),
    ]

    await make_database(session).list_games(
        status=GameStatus.FINISHED,
        game_type_id=uuid.UUID(int=1),
        scheduled_from=datetime(2026, 11, 1, tzinfo=UTC),
        scheduled_to=datetime(2026, 11, 30, tzinfo=UTC),
        limit=20,
        offset=40,
    )

    assert [compile_sql(s) for s in session.statements] == expected


@pytest.mark.parametrize(
    ("status", "direction"),
    [
        (GameStatus.SCHEDULED, "ASC"),
        (GameStatus.FINISHED, "DESC"),
        (GameStatus.CANCELLED, "DESC"),
    ],
)
async def test_list_games_sorts_by_scheduled_at(
    status: GameStatus, direction: str
) -> None:
    session = FakeSession(total=0, games=[])
    expected = (
        f"SELECT {GAME_COLUMNS} FROM games WHERE games.status = '{status}'"
        f" ORDER BY games.scheduled_at {direction}, games.id {direction}"
        " LIMIT 50 OFFSET 0"
    )

    await make_database(session).list_games(**{**DEFAULT_ARGS, "status": status})

    assert compile_sql(session.statements[1]) == expected


class FakeRowSession:
    """Records executed statements and returns one canned row (or None)."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self.statements: list[Any] = []
        self._row = row

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        result.one_or_none.return_value = self._row
        return result


GAME_TYPE_COLUMNS = (
    "game_types.id AS id_1, game_types.name AS name_1, game_types.description,"
    " game_types.number_pool_size, game_types.number_pick_count,"
    " game_types.ticket_price AS ticket_price_1, game_types.default_jackpot,"
    " game_types.is_active"
)


async def test_get_game_returns_game_and_game_type() -> None:
    game_type = make_game_type()
    game = make_game(game_type_id=game_type.id)
    session = FakeRowSession(row=(game, game_type))

    result = await make_database(session).get_game(game.id)  # type: ignore[arg-type]

    assert result == (game, game_type)


async def test_get_game_returns_none_for_unknown_id() -> None:
    session = FakeRowSession(row=None)

    result = await make_database(session).get_game(uuid.uuid4())  # type: ignore[arg-type]

    assert result is None


async def test_get_game_joins_game_type_and_filters_by_id() -> None:
    session = FakeRowSession(row=None)
    expected = [
        (
            f"SELECT {GAME_COLUMNS}, {GAME_TYPE_COLUMNS} FROM games"
            " JOIN game_types ON games.game_type_id = game_types.id"
            " WHERE games.id = '00000000-0000-0000-0000-000000000001'"
        )
    ]

    await make_database(session).get_game(uuid.UUID(int=1))  # type: ignore[arg-type]

    assert [compile_sql(s) for s in session.statements] == expected
