import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, call

import pytest

from lotto.connectors.models import Game, GameStatus, SortOrder
from lotto.exceptions import InvalidDateRange
from lotto.handlers.handlers_v1 import (
    GameResponse,
    GamesPageResponse,
    list_games_handler,
)

from .factories import make_game


def make_database(games: list[Game]) -> AsyncMock:
    database = AsyncMock()
    database.list_games.return_value = games
    return database


def expected_response(game: Game, **overrides: object) -> GameResponse:
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
    return GameResponse(**fields)


async def test_list_games_passes_filters_to_database() -> None:
    database = make_database([])
    game_type_id = uuid.uuid4()
    scheduled_from = datetime(2026, 11, 1, tzinfo=UTC)
    scheduled_to = datetime(2026, 11, 30, tzinfo=UTC)
    expected = [
        call(
            status=GameStatus.SCHEDULED,
            game_type_id=game_type_id,
            scheduled_from=scheduled_from,
            scheduled_to=scheduled_to,
            order=SortOrder.DESC,
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
        order=SortOrder.DESC,
        limit=10,
        offset=20,
    )

    assert database.list_games.await_args_list == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (GameStatus.SCHEDULED, SortOrder.ASC),
        (GameStatus.FINISHED, SortOrder.DESC),
        (GameStatus.CANCELLED, SortOrder.DESC),
        (None, SortOrder.DESC),
    ],
)
async def test_list_games_chooses_default_order_from_status(
    status: GameStatus | None, expected: SortOrder
) -> None:
    database = make_database([])

    await list_games_handler(database, status, None, None, None, None, 50, 0)

    assert database.list_games.await_args.kwargs["order"] == expected


async def test_list_games_rejects_from_after_to() -> None:
    scheduled_from = datetime(2026, 12, 1, tzinfo=UTC)
    scheduled_to = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(InvalidDateRange):
        await list_games_handler(
            make_database([]), None, None, scheduled_from, scheduled_to, None, 50, 0
        )


async def test_list_games_keeps_seed_and_winning_numbers_of_finished_games() -> None:
    game = make_game(status=GameStatus.FINISHED)
    expected = GamesPageResponse(items=[expected_response(game)])

    page = await list_games_handler(
        make_database([game]), None, None, None, None, None, 50, 0
    )

    assert page == expected


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_list_games_hides_seed_and_winning_numbers_of_unfinished_games(
    status: GameStatus,
) -> None:
    game = make_game(status=status)
    expected = GamesPageResponse(
        items=[expected_response(game, seed=None, winning_numbers=None)]
    )

    page = await list_games_handler(
        make_database([game]), None, None, None, None, None, 50, 0
    )

    assert page == expected


async def test_list_games_returns_empty_page() -> None:
    page = await list_games_handler(
        make_database([]), None, None, None, None, None, 50, 0
    )

    assert page == GamesPageResponse(items=[])
