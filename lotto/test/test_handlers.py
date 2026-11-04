import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, call

import pytest

from lotto.connectors.models import Game, GameStatus
from lotto.handlers.handlers_v1 import (
    GameDetailsView,
    GamesPage,
    GameTypeSummaryView,
    GameView,
    get_game_handler,
    list_games_handler,
)

from .factories import make_game, make_game_type


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


def expected_details(game: Game, **overrides: object) -> GameDetailsView:
    fields = {**vars(expected_view(game)), **overrides}
    return GameDetailsView(
        **fields,
        game_type=GameTypeSummaryView(
            id=game.game_type_id,
            name="6 z 49",
            number_pool_size=49,
            number_pick_count=6,
        ),
    )


def make_get_game_database(game: Game | None) -> AsyncMock:
    database = AsyncMock()
    if game is None:
        database.get_game.return_value = None
    else:
        database.get_game.return_value = (game, make_game_type(id=game.game_type_id))
    return database


async def test_get_game_passes_id_to_database() -> None:
    database = make_get_game_database(None)
    game_id = uuid.uuid4()

    await get_game_handler(database, game_id)

    assert database.get_game.await_args_list == [call(game_id)]


async def test_get_game_returns_finished_game_with_game_type() -> None:
    game = make_game(status=GameStatus.FINISHED)

    view = await get_game_handler(make_get_game_database(game), game.id)

    assert view == expected_details(game)


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_get_game_hides_seed_and_winning_numbers_of_unfinished_game(
    status: GameStatus,
) -> None:
    game = make_game(status=status)

    view = await get_game_handler(make_get_game_database(game), game.id)

    assert view == expected_details(game, seed=None, winning_numbers=None)


async def test_get_game_returns_none_for_unknown_id() -> None:
    view = await get_game_handler(make_get_game_database(None), uuid.uuid4())

    assert view is None
