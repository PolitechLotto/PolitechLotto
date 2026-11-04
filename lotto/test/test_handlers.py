import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, call

import pytest

from lotto.connectors.models import Game, GameStatus
from lotto.handlers.handlers_v1 import GamesPage, GameView, list_games_handler

from .factories import make_game


def make_database(games: list[Game], total: int) -> AsyncMock:
    database = AsyncMock()
    database.list_games.return_value = (games, total)
    return database


def expected_view(game: Game, **overrides: object) -> GameView:
    fields: dict = {
        "id": game.id,
        "name": game.name,
        "game_type_id": game.game_type_id,
        "ticket_price": game.ticket_price,
        "jackpot": game.jackpot,
        "status": game.status,
        "scheduled_at": game.scheduled_at,
        "started_at": game.started_at,
        "finished_at": game.finished_at,
        "seed_hash": game.seed_hash,
        "seed": game.seed,
        "winning_numbers": game.winning_numbers,
    }
    fields.update(overrides)
    return GameView(**fields)


async def test_list_games_passes_filters_to_database() -> None:
    database = make_database([], 0)
    game_type_id = uuid.uuid4()
    scheduled_from = datetime(2026, 11, 1, tzinfo=UTC)
    scheduled_to = datetime(2026, 11, 30, tzinfo=UTC)
    expected = [
        call(
            status=GameStatus.SCHEDULED,
            game_type_id=game_type_id,
            scheduled_from=scheduled_from,
            scheduled_to=scheduled_to,
            limit=10,
            offset=20,
        )
    ]

    await list_games_handler(
        database,
        status=GameStatus.SCHEDULED,
        game_type_id=game_type_id,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        limit=10,
        offset=20,
    )

    assert database.list_games.await_args_list == expected


async def test_list_games_keeps_seed_and_winning_numbers_of_finished_games() -> None:
    game = make_game(status=GameStatus.FINISHED)
    expected = GamesPage(items=[expected_view(game)], total=42)

    page = await list_games_handler(
        make_database([game], 42), None, None, None, None, 50, 0
    )

    assert page == expected


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_list_games_hides_seed_and_winning_numbers_of_unfinished_games(
    status: GameStatus,
) -> None:
    game = make_game(status=status)
    expected = GamesPage(
        items=[expected_view(game, seed=None, winning_numbers=None)], total=1
    )

    page = await list_games_handler(
        make_database([game], 1), None, None, None, None, 50, 0
    )

    assert page == expected


async def test_list_games_returns_empty_page() -> None:
    page = await list_games_handler(make_database([], 0), None, None, None, None, 50, 0)

    assert page == GamesPage(items=[], total=0)
