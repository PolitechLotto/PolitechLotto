import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus, SortOrder

from .factories import make_game


class FakeSession:
    """Records executed statements and returns a canned page of games."""

    def __init__(self, games: list[Any]) -> None:
        self.statements: list[Any] = []
        self._games = games

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
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
    "order": SortOrder.DESC,
    "limit": 50,
    "offset": 0,
}


GAME_COLUMNS = (
    "games.id, games.game_type_id, games.game_schedule_id, games.name, "
    "games.ticket_price, games.jackpot, games.status, games.scheduled_at, "
    "games.started_at, games.finished_at, games.seed_hash, games.seed, "
    "games.winning_numbers"
)


async def test_list_games_returns_games() -> None:
    games = [make_game(), make_game()]
    session = FakeSession(games=games)

    result = await make_database(session).list_games(**DEFAULT_ARGS)

    assert list(result) == games


async def test_list_games_without_filters() -> None:
    session = FakeSession(games=[])
    expected = [
        (
            f"SELECT {GAME_COLUMNS} FROM games"
            " ORDER BY games.scheduled_at DESC, games.id DESC LIMIT 50 OFFSET 0"
        )
    ]

    await make_database(session).list_games(**DEFAULT_ARGS)

    assert [compile_sql(s) for s in session.statements] == expected


async def test_list_games_applies_filters() -> None:
    session = FakeSession(games=[])
    where = (
        "WHERE games.status = 'finished'"
        " AND games.game_type_id = '00000000-0000-0000-0000-000000000001'"
        " AND games.scheduled_at >= '2026-11-01 00:00:00+00:00'"
        " AND games.scheduled_at <= '2026-11-30 00:00:00+00:00'"
    )
    expected = [
        (
            f"SELECT {GAME_COLUMNS} FROM games {where}"
            " ORDER BY games.scheduled_at DESC, games.id DESC LIMIT 20 OFFSET 40"
        )
    ]

    await make_database(session).list_games(
        status=GameStatus.FINISHED,
        game_type_id=uuid.UUID(int=1),
        scheduled_from=datetime(2026, 11, 1, tzinfo=UTC),
        scheduled_to=datetime(2026, 11, 30, tzinfo=UTC),
        order=SortOrder.DESC,
        limit=20,
        offset=40,
    )

    assert [compile_sql(s) for s in session.statements] == expected


@pytest.mark.parametrize(
    ("order", "direction"),
    [
        (SortOrder.ASC, "ASC"),
        (SortOrder.DESC, "DESC"),
    ],
)
async def test_list_games_sorts_by_scheduled_at(
    order: SortOrder, direction: str
) -> None:
    session = FakeSession(games=[])
    expected = (
        f"SELECT {GAME_COLUMNS} FROM games"
        f" ORDER BY games.scheduled_at {direction}, games.id {direction}"
        " LIMIT 50 OFFSET 0"
    )

    await make_database(session).list_games(**{**DEFAULT_ARGS, "order": order})

    assert compile_sql(session.statements[0]) == expected
