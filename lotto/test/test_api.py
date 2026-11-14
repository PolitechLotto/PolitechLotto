import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from lotto.connectors import get_broker, get_database
from lotto.connectors.models import GameStatus
from lotto.main import create_sub_app
from lotto.routers.api_v1 import router

from .conftest import (
    GAME_TYPE_ID,
    FakeBroker,
    FakeDatabase,
    make_game,
    make_game_type,
    make_game_with_type,
)

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


ADMIN_HEADERS = {
    "X-User-Role": "admin",
    "X-User-Id": "22222222-2222-2222-2222-222222222222",
}


@pytest.fixture
async def write_client(
    fake_db: FakeDatabase, fake_broker: FakeBroker
) -> AsyncIterator[httpx.AsyncClient]:
    fake_db.game_types = [make_game_type()]
    app = create_sub_app(title="API", routers=[router])
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_broker] = lambda: fake_broker
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def game_body(**overrides: object) -> dict[str, object]:
    scheduled_at = datetime.now(UTC) + timedelta(days=1)
    return {
        "game_type_id": str(GAME_TYPE_ID),
        "scheduled_at": scheduled_at.isoformat(),
        **overrides,
    }


async def test_create_game_returns_201_without_seed(
    write_client: httpx.AsyncClient, fake_db: FakeDatabase, fake_broker: FakeBroker
) -> None:
    response = await write_client.post(
        URL, json=game_body(name="Mikolajkowe"), headers=ADMIN_HEADERS
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == GAME_KEYS
    assert body["id"] == str(fake_db.games[-1].id)
    assert body["name"] == "Mikolajkowe"
    assert body["status"] == "scheduled"
    assert body["ticket_price"] == 10
    assert body["jackpot"] == 1000
    assert body["seed"] is None
    assert body["winning_numbers"] is None
    assert body["seed_hash"] == fake_db.games[-1].seed_hash
    assert fake_broker.published[0][1]["created_by"] == ADMIN_HEADERS["X-User-Id"]


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-User-Role": "player"}, {"X-User-Role": "ADMIN"}],
)
async def test_create_game_requires_admin(
    write_client: httpx.AsyncClient,
    fake_db: FakeDatabase,
    headers: dict[str, str],
) -> None:
    response = await write_client.post(URL, json=game_body(), headers=headers)

    assert response.status_code == 403
    assert fake_db.games == []


async def test_create_game_non_admin_gets_403_even_with_invalid_body(
    write_client: httpx.AsyncClient,
) -> None:
    response = await write_client.post(
        URL, json={"jackpot": -1}, headers={"X-User-Role": "player"}
    )

    assert response.status_code == 403


async def test_create_game_unknown_game_type_returns_404(
    write_client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    body = game_body(game_type_id=str(uuid.uuid4()))

    response = await write_client.post(URL, json=body, headers=ADMIN_HEADERS)

    assert response.status_code == 404
    assert fake_db.games == []


async def test_create_game_inactive_game_type_returns_422(
    write_client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.game_types = [make_game_type(is_active=False)]

    response = await write_client.post(URL, json=game_body(), headers=ADMIN_HEADERS)

    assert response.status_code == 422
    assert response.json() == {"detail": "Game type is inactive"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"scheduled_at": "2020-01-01T00:00:00Z"},
        {"scheduled_at": "2099-01-01T00:00:00"},
        {"scheduled_at": "tomorrow"},
        {"ticket_price": -1},
        {"jackpot": -1},
        {"name": ""},
        {"game_type_id": "not-a-uuid"},
    ],
)
async def test_create_game_invalid_body_returns_422(
    write_client: httpx.AsyncClient,
    fake_db: FakeDatabase,
    overrides: dict[str, object],
) -> None:
    response = await write_client.post(
        URL, json=game_body(**overrides), headers=ADMIN_HEADERS
    )

    assert response.status_code == 422
    assert fake_db.games == []


@pytest.mark.parametrize("missing", ["game_type_id", "scheduled_at"])
async def test_create_game_missing_required_field_returns_422(
    write_client: httpx.AsyncClient, missing: str
) -> None:
    body = game_body()
    del body[missing]

    response = await write_client.post(URL, json=body, headers=ADMIN_HEADERS)

    assert response.status_code == 422
