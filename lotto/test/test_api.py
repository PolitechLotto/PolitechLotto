from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from lotto.connectors import get_database
from lotto.connectors.models import Game, GameStatus
from lotto.main import create_sub_app
from lotto.routers.api_v1 import router

from .conftest import GAME_TYPE_ID, FakeDatabase, make_game

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
