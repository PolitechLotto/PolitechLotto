import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from lotto.connectors import get_broker, get_database
from lotto.connectors.models import Game, GameStatus
from lotto.main import create_sub_app
from lotto.routers.api_v1 import router

from .conftest import (
    GAME_TYPE_ID,
    GAME_TYPE_NAME,
    NUMBER_PICK_COUNT,
    NUMBER_POOL_SIZE,
    FakeBroker,
    FakeDatabase,
    make_game,
    make_game_type,
    make_game_with_type,
)

URL = "/v1/games"
DEFAULT_LIMIT = 20
DEFAULT_OFFSET = 0
LIMIT = 5
OFFSET = 10
DATE_FROM = datetime(2026, 11, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC)
FINISHED_AT = datetime(2026, 11, 20, tzinfo=UTC)
SCHEDULED_AT_JSON = "2026-11-20T18:00:00Z"
FINISHED_AT_JSON = "2026-11-20T00:00:00Z"
GAME_TYPE_JSON = {
    "id": str(GAME_TYPE_ID),
    "name": GAME_TYPE_NAME,
    "number_pool_size": NUMBER_POOL_SIZE,
    "number_pick_count": NUMBER_PICK_COUNT,
}
ADMIN_ID = "22222222-2222-2222-2222-222222222222"
ADMIN_HEADERS = {"X-User-Role": "admin", "X-User-Id": ADMIN_ID}
CUSTOM_NAME = "Mikolajkowe"
FUTURE_SCHEDULED_AT_JSON = "2099-01-01T18:00:00Z"


def game_json(game: Game, **overrides: Any) -> dict[str, Any]:
    return {
        "id": str(game.id),
        "name": game.name,
        "game_type_id": str(game.game_type_id),
        "ticket_price": game.ticket_price,
        "jackpot": game.jackpot,
        "status": game.status.value,
        "scheduled_at": SCHEDULED_AT_JSON,
        "started_at": None,
        "finished_at": None,
        "seed_hash": game.seed_hash,
        "seed": game.seed,
        "winning_numbers": game.winning_numbers,
    } | overrides


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
    game = make_game(GameStatus.FINISHED, finished_at=FINISHED_AT)
    fake_db.games = [game]
    fake_db.total = 1
    expected_response = {
        "games": [game_json(game, finished_at=FINISHED_AT_JSON)],
        "total": 1,
        "limit": DEFAULT_LIMIT,
        "offset": DEFAULT_OFFSET,
    }

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == expected_response


async def test_list_games_uses_default_query(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    expected_response = {
        "games": [],
        "total": 0,
        "limit": DEFAULT_LIMIT,
        "offset": DEFAULT_OFFSET,
    }

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == expected_response
    assert fake_db.calls == [
        {
            "status": None,
            "game_type_id": None,
            "date_from": None,
            "date_to": None,
            "limit": DEFAULT_LIMIT,
            "offset": DEFAULT_OFFSET,
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
            "from": DATE_FROM.isoformat(),
            "to": DATE_TO.isoformat(),
            "limit": LIMIT,
            "offset": OFFSET,
        },
    )

    assert response.status_code == 200
    assert fake_db.calls == [
        {
            "status": GameStatus.SCHEDULED,
            "game_type_id": GAME_TYPE_ID,
            "date_from": DATE_FROM,
            "date_to": DATE_TO,
            "limit": LIMIT,
            "offset": OFFSET,
        }
    ]


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_list_games_hides_secrets_of_unfinished_games(
    client: httpx.AsyncClient, fake_db: FakeDatabase, status: GameStatus
) -> None:
    game = make_game(status)
    fake_db.games = [game]
    fake_db.total = 1
    expected_response = {
        "games": [game_json(game, seed=None, winning_numbers=None)],
        "total": 1,
        "limit": DEFAULT_LIMIT,
        "offset": DEFAULT_OFFSET,
    }

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == expected_response


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


async def test_get_game_returns_finished_game_with_game_type(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    game = make_game_with_type(GameStatus.FINISHED)
    fake_db.games = [game]
    expected_response = game_json(game, game_type=GAME_TYPE_JSON)

    response = await client.get(f"{URL}/{game.id}")

    assert response.status_code == 200
    assert response.json() == expected_response


@pytest.mark.parametrize("status", [GameStatus.SCHEDULED, GameStatus.CANCELLED])
async def test_get_game_hides_secrets_of_unfinished_game(
    client: httpx.AsyncClient, fake_db: FakeDatabase, status: GameStatus
) -> None:
    game = make_game_with_type(status)
    fake_db.games = [game]
    expected_response = game_json(
        game, seed=None, winning_numbers=None, game_type=GAME_TYPE_JSON
    )

    response = await client.get(f"{URL}/{game.id}")

    assert response.status_code == 200
    assert response.json() == expected_response


async def test_get_game_returns_404_for_unknown_id(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    game_id = uuid.uuid4()

    response = await client.get(f"{URL}/{game_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Game not found"}


async def test_get_game_rejects_invalid_id(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    response = await client.get(f"{URL}/not-a-uuid")

    assert response.status_code == 422
    assert fake_db.calls == []


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


def game_body(**overrides: Any) -> dict[str, Any]:
    return {
        "game_type_id": str(GAME_TYPE_ID),
        "scheduled_at": FUTURE_SCHEDULED_AT_JSON,
    } | overrides


async def test_create_game_returns_201_without_seed(
    write_client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    response = await write_client.post(
        URL, json=game_body(name=CUSTOM_NAME), headers=ADMIN_HEADERS
    )

    stored = fake_db.games[-1]
    expected_response = game_json(
        stored,
        name=CUSTOM_NAME,
        scheduled_at=FUTURE_SCHEDULED_AT_JSON,
        seed=None,
        winning_numbers=None,
    )
    assert response.status_code == 201
    assert response.json() == expected_response


async def test_create_game_passes_admin_id_to_published_event(
    write_client: httpx.AsyncClient, fake_broker: FakeBroker
) -> None:
    await write_client.post(URL, json=game_body(), headers=ADMIN_HEADERS)

    _, payload = fake_broker.published[0]
    assert payload["created_by"] == ADMIN_ID


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
    overrides: dict[str, Any],
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
