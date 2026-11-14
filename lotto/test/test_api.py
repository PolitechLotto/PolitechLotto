import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest

from lotto.connectors import get_database
from lotto.connectors.models import GameStatus
from lotto.main import create_sub_app
from lotto.routers.api_v1 import router

from .conftest import GAME_TYPE_ID, FakeDatabase, make_game, make_game_with_type

URL = "/v1/games"
GAME_KEYS = {
    "id",
    "name",
    "game_type_id",
    "ticket_price",
    "jackpot",
    "status",
    "scheduled_at",
    "started_at",
    "finished_at",
    "seed_hash",
    "seed",
    "winning_numbers",
}


@pytest.fixture
async def client(fake_db: FakeDatabase) -> AsyncIterator[httpx.AsyncClient]:
    app = create_sub_app(title="API", routers=[router])
    app.dependency_overrides[get_database] = lambda: fake_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def test_list_games_returns_paginated_response(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.games = [
        make_game(GameStatus.FINISHED, finished_at=datetime(2026, 11, 20, tzinfo=UTC))
    ]
    fake_db.total = 1

    response = await client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert set(body["items"][0]) == GAME_KEYS
    assert body["items"][0]["status"] == "finished"
    assert body["items"][0]["winning_numbers"] == [1, 2, 3, 4, 5, 6]


async def test_list_games_uses_default_query(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    assert fake_db.calls == [
        {
            "status": None,
            "game_type_id": None,
            "date_from": None,
            "date_to": None,
            "limit": 20,
            "offset": 0,
        }
    ]


async def test_list_games_parses_query_parameters(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    response = await client.get(
        URL,
        params={
            "status": "scheduled",
            "game_type_id": str(GAME_TYPE_ID),
            "from": "2026-11-01T00:00:00Z",
            "to": "2026-11-30T23:59:59Z",
            "limit": 5,
            "offset": 10,
        },
    )

    assert response.status_code == 200
    assert fake_db.calls == [
        {
            "status": GameStatus.SCHEDULED,
            "game_type_id": GAME_TYPE_ID,
            "date_from": datetime(2026, 11, 1, tzinfo=UTC),
            "date_to": datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC),
            "limit": 5,
            "offset": 10,
        }
    ]


async def test_list_games_hides_secrets_of_unfinished_games(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.games = [make_game(GameStatus.SCHEDULED), make_game(GameStatus.CANCELLED)]

    response = await client.get(URL)

    for item in response.json()["items"]:
        assert item["seed"] is None
        assert item["winning_numbers"] is None
        assert item["seed_hash"] == "hash"


@pytest.mark.parametrize(
    "params",
    [
        {"status": "in_progress"},
        {"game_type_id": "not-a-uuid"},
        {"from": "yesterday"},
        {"to": "tomorrow"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
async def test_list_games_rejects_invalid_query(
    client: httpx.AsyncClient, fake_db: FakeDatabase, params: dict[str, str | int]
) -> None:
    response = await client.get(URL, params=params)

    assert response.status_code == 422
    assert fake_db.calls == []


async def test_get_game_returns_game_with_game_type(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    game = make_game_with_type(GameStatus.FINISHED)
    fake_db.games = [game]

    response = await client.get(f"{URL}/{game.id}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == GAME_KEYS | {"game_type"}
    assert body["id"] == str(game.id)
    assert body["seed"] == "secret-seed"
    assert body["winning_numbers"] == [1, 2, 3, 4, 5, 6]
    assert body["game_type"] == {
        "id": str(GAME_TYPE_ID),
        "name": "Lotto",
        "number_pool_size": 49,
        "number_pick_count": 6,
    }


async def test_get_game_hides_secrets_of_unfinished_game(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    game = make_game_with_type(GameStatus.SCHEDULED)
    fake_db.games = [game]

    body = (await client.get(f"{URL}/{game.id}")).json()

    assert body["seed"] is None
    assert body["winning_numbers"] is None
    assert body["seed_hash"] == "hash"


async def test_get_game_returns_404_for_unknown_id(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    game_id = uuid.uuid4()

    response = await client.get(f"{URL}/{game_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Game not found"}
    assert fake_db.calls == [{"game_id": game_id}]


async def test_get_game_rejects_invalid_id(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    response = await client.get(f"{URL}/not-a-uuid")

    assert response.status_code == 422
    assert fake_db.calls == []
