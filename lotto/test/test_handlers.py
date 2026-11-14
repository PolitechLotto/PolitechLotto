from datetime import UTC, datetime
from typing import cast

import pytest

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import list_games_handler

from .conftest import GAME_TYPE_ID, FakeDatabase, make_game


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
