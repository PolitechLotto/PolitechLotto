import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from lotto.connectors.broker import MessageBroker
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import (
    GAME_CREATED_EVENT,
    GameCreate,
    GameOut,
    GameTypeNotFoundError,
    InvalidGameError,
    create_game_handler,
    get_game_handler,
    list_games_handler,
)

from .conftest import (
    GAME_TYPE_ID,
    FakeBroker,
    FakeDatabase,
    make_game,
    make_game_type,
    make_game_with_type,
)


async def test_passes_filters_and_pagination_to_database(fake_db: FakeDatabase) -> None:
    date_from = datetime(2026, 11, 1, tzinfo=UTC)
    date_to = datetime(2026, 11, 30, tzinfo=UTC)

    await list_games_handler(
        cast(Database, fake_db),
        GameStatus.FINISHED,
        GAME_TYPE_ID,
        date_from,
        date_to,
        10,
        20,
    )

    assert fake_db.calls == [
        {
            "status": GameStatus.FINISHED,
            "game_type_id": GAME_TYPE_ID,
            "date_from": date_from,
            "date_to": date_to,
            "limit": 10,
            "offset": 20,
        }
    ]


async def test_returns_pagination_metadata() -> None:
    db = FakeDatabase([make_game()], total=42)

    page = await list_games_handler(cast(Database, db), None, None, None, None, 1, 5)

    assert page.total == 42
    assert page.limit == 1
    assert page.offset == 5
    assert len(page.items) == 1


async def test_keeps_seed_and_winning_numbers_for_finished_games() -> None:
    game = make_game(GameStatus.FINISHED, seed="revealed", winning_numbers=[7, 8, 9])
    db = FakeDatabase([game])

    page = await list_games_handler(cast(Database, db), None, None, None, None, 20, 0)

    assert page.items[0].seed == "revealed"
    assert page.items[0].winning_numbers == [7, 8, 9]


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_hides_seed_and_winning_numbers_for_unfinished_games(
    status: GameStatus,
) -> None:
    game = make_game(status, seed="secret", winning_numbers=[1, 2, 3])
    db = FakeDatabase([game])

    page = await list_games_handler(cast(Database, db), None, None, None, None, 20, 0)

    item = page.items[0]
    assert item.seed is None
    assert item.winning_numbers is None
    assert item.seed_hash == "hash"


async def test_maps_all_public_fields() -> None:
    game = make_game(GameStatus.FINISHED)
    db = FakeDatabase([game])

    page = await list_games_handler(cast(Database, db), None, None, None, None, 20, 0)

    item = page.items[0]
    assert item.id == game.id
    assert item.name == game.name
    assert item.game_type_id == game.game_type_id
    assert item.ticket_price == game.ticket_price
    assert item.jackpot == game.jackpot
    assert item.status is GameStatus.FINISHED
    assert item.scheduled_at == game.scheduled_at
    assert item.started_at is None
    assert item.finished_at is None


async def test_mixed_statuses_are_masked_independently() -> None:
    games = [make_game(GameStatus.FINISHED), make_game(GameStatus.SCHEDULED)]
    db = FakeDatabase(games)

    page = await list_games_handler(cast(Database, db), None, None, None, None, 20, 0)

    assert page.items[0].seed == "secret-seed"
    assert page.items[1].seed is None


async def test_get_game_returns_game_with_game_type() -> None:
    game = make_game_with_type(GameStatus.FINISHED)
    db = FakeDatabase([game])

    details = await get_game_handler(cast(Database, db), game.id)

    assert details is not None
    assert details.id == game.id
    assert details.seed == "secret-seed"
    assert details.winning_numbers == [1, 2, 3, 4, 5, 6]
    assert details.game_type.id == GAME_TYPE_ID
    assert details.game_type.name == "Lotto"
    assert details.game_type.number_pool_size == 49
    assert details.game_type.number_pick_count == 6
    assert db.calls == [{"game_id": game.id}]


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_get_game_hides_seed_and_winning_numbers_for_unfinished_game(
    status: GameStatus,
) -> None:
    game = make_game_with_type(status)
    db = FakeDatabase([game])

    details = await get_game_handler(cast(Database, db), game.id)

    assert details is not None
    assert details.seed is None
    assert details.winning_numbers is None
    assert details.seed_hash == "hash"
    assert details.game_type.name == "Lotto"


async def test_get_game_returns_none_for_unknown_id() -> None:
    db = FakeDatabase([make_game_with_type()])

    assert await get_game_handler(cast(Database, db), uuid.uuid4()) is None


ADMIN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


def db_with_game_type(**overrides: object) -> FakeDatabase:
    db = FakeDatabase()
    db.game_types = [make_game_type(**overrides)]
    return db


async def create(
    db: FakeDatabase, broker: FakeBroker | None = None, **fields: object
) -> tuple[GameOut, FakeBroker]:
    broker = broker or FakeBroker()
    data = GameCreate.model_validate(
        {"game_type_id": GAME_TYPE_ID, "scheduled_at": future(), **fields}
    )
    game = await create_game_handler(
        cast(Database, db), cast(MessageBroker, broker), data, ADMIN_ID
    )
    return game, broker


async def test_create_game_copies_price_and_jackpot_from_game_type() -> None:
    db = db_with_game_type(ticket_price=15, default_jackpot=5000)

    await create(db)

    new_game = db.calls[-1]["create_game"]
    assert new_game.ticket_price == 15
    assert new_game.jackpot == 5000


async def test_create_game_uses_given_price_jackpot_and_name() -> None:
    db = db_with_game_type()

    await create(db, name="Mikolajkowe", ticket_price=0, jackpot=99)

    new_game = db.calls[-1]["create_game"]
    assert new_game.name == "Mikolajkowe"
    assert new_game.ticket_price == 0
    assert new_game.jackpot == 99


async def test_create_game_default_name_is_type_name_and_next_number() -> None:
    db = db_with_game_type(name="Lotto")
    db.games = [make_game(), make_game(), make_game(game_type_id=uuid.uuid4())]

    await create(db)

    assert db.calls[-1]["create_game"].name == "Lotto #3"


async def test_create_game_generates_seed_and_sha256_hash() -> None:
    db = db_with_game_type()

    await create(db)
    await create(db)

    first = db.calls[-2]["create_game"]
    second = db.calls[-1]["create_game"]
    assert len(first.seed) == 64
    assert first.seed_hash == hashlib.sha256(first.seed.encode()).hexdigest()
    assert first.seed != second.seed


async def test_create_game_returns_scheduled_game_without_seed() -> None:
    db = db_with_game_type()
    scheduled_at = future()

    game, _ = await create(db, scheduled_at=scheduled_at)

    stored = db.games[-1]
    assert game.id == stored.id
    assert game.status is GameStatus.SCHEDULED
    assert game.scheduled_at == scheduled_at
    assert game.seed is None
    assert game.winning_numbers is None
    assert game.seed_hash == stored.seed_hash


async def test_create_game_publishes_game_created_without_seed() -> None:
    db = db_with_game_type()

    _, broker = await create(db, name="Test", ticket_price=10, jackpot=100)

    stored = db.games[-1]
    assert broker.published == [
        (
            GAME_CREATED_EVENT,
            {
                "game_id": str(stored.id),
                "game_type_id": str(GAME_TYPE_ID),
                "name": "Test",
                "ticket_price": 10,
                "jackpot": 100,
                "scheduled_at": stored.scheduled_at.isoformat(),
                "seed_hash": stored.seed_hash,
                "created_by": str(ADMIN_ID),
            },
        )
    ]


async def test_create_game_still_returns_game_when_publish_fails() -> None:
    db = db_with_game_type()

    game, _ = await create(db, FakeBroker(error=ConnectionError("down")))

    assert game.id == db.games[-1].id


async def test_create_game_unknown_game_type() -> None:
    with pytest.raises(GameTypeNotFoundError):
        await create(FakeDatabase())


async def test_create_game_inactive_game_type() -> None:
    db = db_with_game_type(is_active=False)

    with pytest.raises(InvalidGameError, match="inactive"):
        await create(db)

    assert db.games == []


@pytest.mark.parametrize("delta", [timedelta(seconds=-1), timedelta(days=-30)])
async def test_create_game_scheduled_at_in_past(delta: timedelta) -> None:
    db = db_with_game_type()
    broker = FakeBroker()

    with pytest.raises(InvalidGameError, match="future"):
        await create(db, broker, scheduled_at=datetime.now(UTC) + delta)

    assert db.games == []
    assert broker.published == []
