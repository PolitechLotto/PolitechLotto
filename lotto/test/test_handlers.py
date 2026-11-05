import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, call

import pytest

from lotto.connectors.models import GameStatus, GameType
from lotto.handlers import handlers_v1
from lotto.handlers.handlers_v1 import (
    CreateGameData,
    GameTypeInactiveError,
    GameTypeNotFoundError,
    GameView,
    ScheduledAtNotInFutureError,
    SeedCommitment,
    create_game_handler,
    generate_seed,
)

from .factories import make_game, make_game_type

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
SCHEDULED_AT = datetime(2026, 12, 1, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        handlers_v1,
        "generate_seed",
        lambda: SeedCommitment(seed="seed", seed_hash="hash"),
    )


def make_database(game_type: GameType | None, games_count: int = 0) -> AsyncMock:
    database = AsyncMock()
    database.get_game_type.return_value = game_type
    database.count_games.return_value = games_count

    async def create_game(data: dict[str, Any]) -> Any:
        return make_game(
            **data, started_at=None, finished_at=None, winning_numbers=None
        )

    database.create_game.side_effect = create_game
    return database


def make_data(game_type: GameType, **overrides: Any) -> CreateGameData:
    fields: dict[str, Any] = {
        "game_type_id": game_type.id,
        "scheduled_at": SCHEDULED_AT,
    }
    fields.update(overrides)
    return CreateGameData(**fields)


def expected_new_game(game_type: GameType, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "game_type_id": game_type.id,
        "game_schedule_id": None,
        "name": "6 z 49 #1",
        "ticket_price": 10,
        "jackpot": 1000,
        "status": GameStatus.SCHEDULED,
        "scheduled_at": SCHEDULED_AT,
        "seed_hash": "hash",
        "seed": "seed",
    }
    fields.update(overrides)
    return fields


async def test_create_game_copies_price_and_jackpot_from_game_type() -> None:
    game_type = make_game_type(ticket_price=15, default_jackpot=5000)
    database = make_database(game_type)

    await create_game_handler(database, make_data(game_type), NOW)

    assert database.create_game.await_args_list == [
        call(expected_new_game(game_type, ticket_price=15, jackpot=5000))
    ]


async def test_create_game_uses_given_name_price_and_jackpot() -> None:
    game_type = make_game_type()
    database = make_database(game_type)
    data = make_data(game_type, name="Mikołajki", ticket_price=0, jackpot=99)

    await create_game_handler(database, data, NOW)

    assert database.create_game.await_args_list == [
        call(expected_new_game(game_type, name="Mikołajki", ticket_price=0, jackpot=99))
    ]
    assert database.count_games.await_count == 0


async def test_create_game_numbers_default_name_after_existing_games() -> None:
    game_type = make_game_type(name="Mini Lotto")
    database = make_database(game_type, games_count=41)

    view = await create_game_handler(database, make_data(game_type), NOW)

    assert (view.name, database.count_games.await_args_list) == (
        "Mini Lotto #42",
        [call(game_type.id)],
    )


async def test_create_game_returns_game_without_seed() -> None:
    game_type = make_game_type()

    view = await create_game_handler(
        make_database(game_type), make_data(game_type), NOW
    )

    assert view == GameView(
        id=view.id,
        name="6 z 49 #1",
        game_type_id=game_type.id,
        ticket_price=10,
        jackpot=1000,
        status=GameStatus.SCHEDULED,
        scheduled_at=SCHEDULED_AT,
        started_at=None,
        finished_at=None,
        seed_hash="hash",
        seed=None,
        winning_numbers=None,
    )


async def test_create_game_raises_for_unknown_game_type() -> None:
    database = make_database(None)

    with pytest.raises(GameTypeNotFoundError):
        await create_game_handler(database, make_data(make_game_type()), NOW)

    assert database.create_game.await_count == 0


async def test_create_game_raises_for_inactive_game_type() -> None:
    game_type = make_game_type(is_active=False)
    database = make_database(game_type)

    with pytest.raises(GameTypeInactiveError):
        await create_game_handler(database, make_data(game_type), NOW)

    assert database.create_game.await_count == 0


@pytest.mark.parametrize(
    "scheduled_at", [NOW, datetime(2026, 11, 5, 11, 59, tzinfo=UTC)]
)
async def test_create_game_raises_when_scheduled_at_is_not_in_future(
    scheduled_at: datetime,
) -> None:
    game_type = make_game_type()
    database = make_database(game_type)

    with pytest.raises(ScheduledAtNotInFutureError):
        await create_game_handler(
            database, make_data(game_type, scheduled_at=scheduled_at), NOW
        )

    assert database.create_game.await_count == 0


def test_generate_seed_hashes_seed_with_sha256() -> None:
    commitment = generate_seed()

    assert (
        commitment.seed_hash
        == hashlib.sha256(bytes.fromhex(commitment.seed)).hexdigest()
    )


def test_generate_seed_returns_different_seeds() -> None:
    assert generate_seed().seed != generate_seed().seed


async def test_create_game_passes_game_type_id_to_database() -> None:
    game_type_id = uuid.uuid4()
    database = make_database(None)

    with pytest.raises(GameTypeNotFoundError):
        await create_game_handler(
            database,
            CreateGameData(game_type_id=game_type_id, scheduled_at=SCHEDULED_AT),
            NOW,
        )

    assert database.get_game_type.await_args_list == [call(game_type_id)]
