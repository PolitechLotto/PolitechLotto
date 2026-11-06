import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from lotto.connectors.db import Database, NewGame
from lotto.connectors.models import GameStatus

from .factories import make_game, make_game_type


class FakeSession:
    """Records executed statements and commits, and returns one canned result."""

    def __init__(self, result: Any = None) -> None:
        self.statements: list[Any] = []
        self.commits = 0
        self._result = result

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        result.scalar_one.return_value = self._result
        result.scalar_one_or_none.return_value = self._result
        return result

    async def commit(self) -> None:
        self.commits += 1


def compile_sql(statement: Any) -> str:
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    return " ".join(sql.split())


def make_database(session: FakeSession) -> Database:
    return Database(session_factory=lambda: session)  # type: ignore[arg-type,return-value]


GAME_COLUMNS = (
    "games.id, games.game_type_id, games.game_schedule_id, games.name, "
    "games.ticket_price, games.jackpot, games.status, games.scheduled_at, "
    "games.started_at, games.finished_at, games.seed_hash, games.seed, "
    "games.winning_numbers"
)

GAME_TYPE_COLUMNS = (
    "game_types.id, game_types.name, game_types.description,"
    " game_types.number_pool_size, game_types.number_pick_count,"
    " game_types.ticket_price, game_types.default_jackpot,"
    " game_types.is_active"
)


async def test_get_game_type_returns_game_type() -> None:
    game_type = make_game_type()
    session = FakeSession(result=game_type)

    result = await make_database(session).get_game_type(game_type.id)

    assert result is game_type


async def test_get_game_type_returns_none_for_unknown_id() -> None:
    session = FakeSession(result=None)

    result = await make_database(session).get_game_type(uuid.uuid4())

    assert result is None


async def test_get_game_type_filters_by_id() -> None:
    session = FakeSession()
    expected = [
        (
            f"SELECT {GAME_TYPE_COLUMNS} FROM game_types"
            " WHERE game_types.id = '00000000-0000-0000-0000-000000000001'"
        )
    ]

    await make_database(session).get_game_type(uuid.UUID(int=1))

    assert [compile_sql(s) for s in session.statements] == expected


async def test_count_games_counts_games_of_game_type() -> None:
    session = FakeSession(result=4)
    expected = [
        (
            "SELECT count(*) AS count_1 FROM games"
            " WHERE games.game_type_id = '00000000-0000-0000-0000-000000000001'"
        )
    ]

    total = await make_database(session).count_games(uuid.UUID(int=1))

    assert (total, [compile_sql(s) for s in session.statements]) == (4, expected)


def make_new_game() -> NewGame:
    return {
        "game_type_id": uuid.UUID(int=1),
        "game_schedule_id": None,
        "name": "6 z 49 #1",
        "ticket_price": 10,
        "jackpot": 1000,
        "status": GameStatus.SCHEDULED,
        "scheduled_at": datetime(2026, 12, 1, 18, 0, tzinfo=UTC),
        "seed_hash": "hash",
        "seed": "seed",
    }


async def test_create_game_inserts_row_and_returns_it() -> None:
    game = make_game(status=GameStatus.SCHEDULED)
    session = FakeSession(result=game)

    result = await make_database(session).create_game(make_new_game())

    assert (result, session.commits) == (game, 1)


async def test_create_game_inserts_given_values() -> None:
    session = FakeSession(result=make_game())
    expected = [
        (
            "INSERT INTO games (id, game_type_id, game_schedule_id, name, ticket_price,"
            " jackpot, status, scheduled_at, seed_hash, seed) VALUES"
            " ('00000000-0000-0000-0000-000000000002',"
            " '00000000-0000-0000-0000-000000000001', NULL, '6 z 49 #1', 10, 1000,"
            " 'scheduled', '2026-12-01 18:00:00+00:00', 'hash', 'seed')"
            f" RETURNING {GAME_COLUMNS}"
        )
    ]

    await make_database(session).create_game(
        {**make_new_game(), "id": uuid.UUID(int=2)}  # type: ignore[typeddict-unknown-key]
    )

    assert [compile_sql(s) for s in session.statements] == expected
