import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from lotto.connectors import get_database
from lotto.connectors.models import GameStatus, SortOrder
from lotto.exceptions import InvalidDateRange
from lotto.handlers.handlers_v1 import GameResponse, GamesPageResponse
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
    mock = AsyncMock(return_value=GamesPageResponse(items=[]))
    monkeypatch.setattr(api_v1, "list_games_handler", mock)
    yield mock


def make_game_response(**overrides: object) -> GameResponse:
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
    return GameResponse(**fields)


async def test_list_games_returns_paginated_games(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    handler.return_value = GamesPageResponse(items=[make_game_response()])
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
            order=None,
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
            order=SortOrder.ASC,
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
            "order": "asc",
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
        {"order": "sideways"},
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


async def test_list_games_returns_422_for_invalid_date_range(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    handler.side_effect = InvalidDateRange
    expected = (422, {"detail": "`from` must not be after `to`."})

    response = await client.get(f"{prefix}/games")

    assert (response.status_code, response.json()) == expected
