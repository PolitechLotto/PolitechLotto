import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from lotto.connectors import get_database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import (
    GameDetailsView,
    GamesPage,
    GameTypeSummaryView,
    GameView,
)
from lotto.main import create_sub_app
from lotto.routers import api_v1
from lotto.routers.api_v1 import router

app = create_sub_app(title="API", routers=[router])
prefix = "/v1"

database = MagicMock()
app.dependency_overrides[get_database] = lambda: database


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(return_value=GamesPage(items=[], total=0))
    monkeypatch.setattr(api_v1, "list_games_handler", mock)
    yield mock


def make_game_view(**overrides: object) -> GameView:
    fields: dict = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "name": "6 z 49",
        "game_type_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "ticket_price": 10,
        "jackpot": 1000,
        "status": GameStatus.SCHEDULED,
        "scheduled_at": datetime(2026, 11, 1, 18, 0, tzinfo=UTC),
        "started_at": None,
        "finished_at": None,
        "seed_hash": "hash",
        "seed": None,
        "winning_numbers": None,
    }
    fields.update(overrides)
    return GameView(**fields)


async def test_list_games_returns_paginated_games(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    handler.return_value = GamesPage(items=[make_game_view()], total=3)
    expected = {
        "items": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "6 z 49",
                "game_type_id": "22222222-2222-2222-2222-222222222222",
                "ticket_price": 10,
                "jackpot": 1000,
                "status": "scheduled",
                "scheduled_at": "2026-11-01T18:00:00Z",
                "started_at": None,
                "finished_at": None,
                "seed_hash": "hash",
                "seed": None,
                "winning_numbers": None,
            }
        ],
        "total": 3,
    }

    response = await client.get(f"{prefix}/games")

    assert (response.status_code, response.json()) == (200, expected)


async def test_list_games_uses_default_query(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            status=None,
            game_type_id=None,
            scheduled_from=None,
            scheduled_to=None,
            limit=50,
            offset=0,
        )
    ]

    await client.get(f"{prefix}/games")

    assert handler.await_args_list == expected


async def test_list_games_passes_query_to_handler(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            status=GameStatus.FINISHED,
            game_type_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            scheduled_from=datetime(2026, 11, 1, tzinfo=UTC),
            scheduled_to=datetime(2026, 11, 29, 23, 0, tzinfo=UTC),
            limit=200,
            offset=20,
        )
    ]

    await client.get(
        f"{prefix}/games",
        params={
            "status": "finished",
            "game_type_id": "22222222-2222-2222-2222-222222222222",
            "from": "2026-11-01T00:00:00Z",
            "to": "2026-11-30T00:00:00+01:00",
            "limit": 200,
            "offset": 20,
        },
    )

    assert handler.await_args_list == expected


@pytest.mark.parametrize(
    "params",
    [
        {"status": "in_progress"},
        {"game_type_id": "not-a-uuid"},
        {"from": "yesterday"},
        {"from": "2026-11-01T00:00:00"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ],
)
async def test_list_games_rejects_invalid_query(
    client: httpx.AsyncClient, handler: AsyncMock, params: dict
) -> None:
    response = await client.get(f"{prefix}/games", params=params)

    assert (response.status_code, handler.await_count) == (422, 0)


GAME_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def get_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(api_v1, "get_game_handler", mock)
    yield mock


def make_game_details_view(**overrides: object) -> GameDetailsView:
    return GameDetailsView(
        **vars(make_game_view(**overrides)),
        game_type=GameTypeSummaryView(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="6 z 49",
            number_pool_size=49,
            number_pick_count=6,
        ),
    )


async def test_get_game_returns_game_with_game_type(
    client: httpx.AsyncClient, get_handler: AsyncMock
) -> None:
    get_handler.return_value = make_game_details_view(
        status=GameStatus.FINISHED,
        finished_at=datetime(2026, 11, 1, 18, 5, tzinfo=UTC),
        seed="seed",
        winning_numbers=[1, 2, 3, 4, 5, 6],
    )
    expected = {
        "id": GAME_ID,
        "name": "6 z 49",
        "game_type_id": "22222222-2222-2222-2222-222222222222",
        "ticket_price": 10,
        "jackpot": 1000,
        "status": "finished",
        "scheduled_at": "2026-11-01T18:00:00Z",
        "started_at": None,
        "finished_at": "2026-11-01T18:05:00Z",
        "seed_hash": "hash",
        "seed": "seed",
        "winning_numbers": [1, 2, 3, 4, 5, 6],
        "game_type": {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "6 z 49",
            "number_pool_size": 49,
            "number_pick_count": 6,
        },
    }

    response = await client.get(f"{prefix}/games/{GAME_ID}")

    assert (response.status_code, response.json()) == (200, expected)


async def test_get_game_passes_id_to_handler(
    client: httpx.AsyncClient, get_handler: AsyncMock
) -> None:
    get_handler.return_value = make_game_details_view()

    await client.get(f"{prefix}/games/{GAME_ID}")

    assert get_handler.await_args_list == [call(database, uuid.UUID(GAME_ID))]


async def test_get_game_returns_404_for_unknown_id(
    client: httpx.AsyncClient, get_handler: AsyncMock
) -> None:
    response = await client.get(f"{prefix}/games/{GAME_ID}")

    assert (response.status_code, response.json()) == (
        404,
        {"detail": "Game not found."},
    )


async def test_get_game_rejects_invalid_id(
    client: httpx.AsyncClient, get_handler: AsyncMock
) -> None:
    response = await client.get(f"{prefix}/games/not-a-uuid")

    assert (response.status_code, get_handler.await_count) == (422, 0)
