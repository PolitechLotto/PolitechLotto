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
    GameTypeNotFoundError,
    InvalidGameError,
    create_game_handler,
    get_game_handler,
    list_games_handler,
)
from lotto.handlers.models import (
    Game,
    GameCreate,
    GameDetails,
    GamesPage,
    GameTypeSummary,
)

from .conftest import (
    GAME_NAME,
    GAME_TYPE_ID,
    GAME_TYPE_NAME,
    JACKPOT,
    NUMBER_PICK_COUNT,
    NUMBER_POOL_SIZE,
    SCHEDULED_AT,
    SEED,
    SEED_HASH,
    TICKET_PRICE,
    WINNING_NUMBERS,
    FakeBroker,
    FakeDatabase,
    make_game,
    make_game_type,
    make_game_with_type,
)

DATE_FROM = datetime(2026, 11, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 11, 30, tzinfo=UTC)
LIMIT = 10
OFFSET = 20
TOTAL = 42
ADMIN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
CUSTOM_NAME = "Mikolajkowe"
CUSTOM_TICKET_PRICE = 0
CUSTOM_JACKPOT = 99
TYPE_TICKET_PRICE = 15
TYPE_JACKPOT = 5000
EXISTING_GAMES_OF_TYPE = 2
SEED_LENGTH = 64
ONE_DAY = timedelta(days=1)


async def test_passes_filters_and_pagination_to_database(fake_db: FakeDatabase) -> None:
    await list_games_handler(
        cast(Database, fake_db),
        GameStatus.FINISHED,
        GAME_TYPE_ID,
        DATE_FROM,
        DATE_TO,
        LIMIT,
        OFFSET,
    )

    assert fake_db.calls == [
        {
            "status": GameStatus.FINISHED,
            "game_type_id": GAME_TYPE_ID,
            "date_from": DATE_FROM,
            "date_to": DATE_TO,
            "limit": LIMIT,
            "offset": OFFSET,
        }
    ]


async def test_returns_finished_game_with_pagination_metadata() -> None:
    game = make_game(GameStatus.FINISHED)
    db = FakeDatabase([game], total=TOTAL)
    expected_page = GamesPage(
        games=[
            Game(
                id=game.id,
                name=GAME_NAME,
                game_type_id=GAME_TYPE_ID,
                ticket_price=TICKET_PRICE,
                jackpot=JACKPOT,
                status=GameStatus.FINISHED,
                scheduled_at=SCHEDULED_AT,
                started_at=None,
                finished_at=None,
                seed_hash=SEED_HASH,
                seed=SEED,
                winning_numbers=WINNING_NUMBERS,
            )
        ],
        total=TOTAL,
        limit=LIMIT,
        offset=OFFSET,
    )

    page = await list_games_handler(
        cast(Database, db), None, None, None, None, LIMIT, OFFSET
    )

    assert page == expected_page


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_hides_seed_and_winning_numbers_for_unfinished_games(
    status: GameStatus,
) -> None:
    db = FakeDatabase([make_game(status)])

    page = await list_games_handler(
        cast(Database, db), None, None, None, None, LIMIT, OFFSET
    )

    game = page.games[0]
    assert game.seed is None
    assert game.winning_numbers is None
    assert game.seed_hash == SEED_HASH


async def test_mixed_statuses_are_masked_independently() -> None:
    games = [make_game(GameStatus.FINISHED), make_game(GameStatus.SCHEDULED)]
    db = FakeDatabase(games)

    page = await list_games_handler(
        cast(Database, db), None, None, None, None, LIMIT, OFFSET
    )

    assert page.games[0].seed == SEED
    assert page.games[1].seed is None


async def test_get_game_returns_finished_game_with_game_type() -> None:
    game = make_game_with_type(GameStatus.FINISHED)
    db = FakeDatabase([game])
    expected_details = GameDetails(
        id=game.id,
        name=GAME_NAME,
        game_type_id=GAME_TYPE_ID,
        ticket_price=TICKET_PRICE,
        jackpot=JACKPOT,
        status=GameStatus.FINISHED,
        scheduled_at=SCHEDULED_AT,
        started_at=None,
        finished_at=None,
        seed_hash=SEED_HASH,
        seed=SEED,
        winning_numbers=WINNING_NUMBERS,
        game_type=GameTypeSummary(
            id=GAME_TYPE_ID,
            name=GAME_TYPE_NAME,
            number_pool_size=NUMBER_POOL_SIZE,
            number_pick_count=NUMBER_PICK_COUNT,
        ),
    )

    details = await get_game_handler(cast(Database, db), game.id)

    assert details == expected_details


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
    assert details.seed_hash == SEED_HASH


async def test_get_game_returns_none_for_unknown_id() -> None:
    db = FakeDatabase([make_game_with_type()])

    assert await get_game_handler(cast(Database, db), uuid.uuid4()) is None


def db_with_game_type(**overrides: object) -> FakeDatabase:
    db = FakeDatabase()
    db.game_types = [make_game_type(**overrides)]
    return db


async def create(
    db: FakeDatabase, broker: FakeBroker | None = None, **fields: object
) -> Game:
    data = GameCreate.model_validate(
        {
            "game_type_id": GAME_TYPE_ID,
            "scheduled_at": datetime.now(UTC) + ONE_DAY,
            **fields,
        }
    )
    return await create_game_handler(
        cast(Database, db), cast(MessageBroker, broker or FakeBroker()), data, ADMIN_ID
    )


async def test_create_game_copies_price_and_jackpot_from_game_type() -> None:
    db = db_with_game_type(ticket_price=TYPE_TICKET_PRICE, default_jackpot=TYPE_JACKPOT)

    await create(db)

    new_game = db.calls[-1]["create_game"]
    assert new_game.ticket_price == TYPE_TICKET_PRICE
    assert new_game.jackpot == TYPE_JACKPOT


async def test_create_game_uses_given_name_price_and_jackpot() -> None:
    db = db_with_game_type()

    await create(
        db, name=CUSTOM_NAME, ticket_price=CUSTOM_TICKET_PRICE, jackpot=CUSTOM_JACKPOT
    )

    new_game = db.calls[-1]["create_game"]
    assert new_game.name == CUSTOM_NAME
    assert new_game.ticket_price == CUSTOM_TICKET_PRICE
    assert new_game.jackpot == CUSTOM_JACKPOT


async def test_create_game_default_name_is_type_name_and_next_number() -> None:
    db = db_with_game_type()
    db.games = [make_game() for _ in range(EXISTING_GAMES_OF_TYPE)]
    db.games.append(make_game(game_type_id=uuid.uuid4()))

    await create(db)

    expected_name = f"{GAME_TYPE_NAME} #{EXISTING_GAMES_OF_TYPE + 1}"
    assert db.calls[-1]["create_game"].name == expected_name


async def test_create_game_generates_unique_seed_and_sha256_hash() -> None:
    db = db_with_game_type()

    await create(db)
    await create(db)

    first = db.calls[-2]["create_game"]
    second = db.calls[-1]["create_game"]
    assert len(first.seed) == SEED_LENGTH
    assert first.seed_hash == hashlib.sha256(first.seed.encode()).hexdigest()
    assert first.seed != second.seed


async def test_create_game_returns_scheduled_game_without_seed() -> None:
    db = db_with_game_type()
    scheduled_at = datetime.now(UTC) + ONE_DAY

    game = await create(db, scheduled_at=scheduled_at)

    stored = db.games[-1]
    expected_game = Game(
        id=stored.id,
        name=f"{GAME_TYPE_NAME} #1",
        game_type_id=GAME_TYPE_ID,
        ticket_price=TICKET_PRICE,
        jackpot=JACKPOT,
        status=GameStatus.SCHEDULED,
        scheduled_at=scheduled_at,
        started_at=None,
        finished_at=None,
        seed_hash=stored.seed_hash,
        seed=None,
        winning_numbers=None,
    )
    assert game == expected_game


async def test_create_game_publishes_game_created_without_seed() -> None:
    db = db_with_game_type()
    broker = FakeBroker()

    await create(db, broker, name=CUSTOM_NAME)

    stored = db.games[-1]
    expected_event = (
        GAME_CREATED_EVENT,
        {
            "game_id": str(stored.id),
            "game_type_id": str(GAME_TYPE_ID),
            "name": CUSTOM_NAME,
            "ticket_price": TICKET_PRICE,
            "jackpot": JACKPOT,
            "scheduled_at": stored.scheduled_at.isoformat(),
            "seed_hash": stored.seed_hash,
            "created_by": str(ADMIN_ID),
        },
    )
    assert broker.published == [expected_event]


async def test_create_game_still_returns_game_when_publish_fails() -> None:
    db = db_with_game_type()

    game = await create(db, FakeBroker(error=ConnectionError("down")))

    assert game.id == db.games[-1].id


async def test_create_game_raises_for_unknown_game_type() -> None:
    with pytest.raises(GameTypeNotFoundError):
        await create(FakeDatabase())


async def test_create_game_raises_for_inactive_game_type() -> None:
    db = db_with_game_type(is_active=False)

    with pytest.raises(InvalidGameError, match="inactive"):
        await create(db)

    assert db.games == []


@pytest.mark.parametrize("delta", [timedelta(seconds=-1), -ONE_DAY])
async def test_create_game_raises_for_scheduled_at_in_past(delta: timedelta) -> None:
    db = db_with_game_type()
    broker = FakeBroker()

    with pytest.raises(InvalidGameError, match="future"):
        await create(db, broker, scheduled_at=datetime.now(UTC) + delta)

    assert db.games == []
    assert broker.published == []
