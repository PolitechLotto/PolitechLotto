import uuid
from datetime import UTC, datetime
from typing import cast

import pytest

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import get_game_handler, list_games_handler
from lotto.handlers.models import Game, GameDetails, GamesPage, GameTypeSummary

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
    FakeDatabase,
    make_game,
    make_game_with_type,
)

DATE_FROM = datetime(2026, 11, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 11, 30, tzinfo=UTC)
LIMIT = 10
OFFSET = 20
TOTAL = 42


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
