import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from lotto.connectors import get_database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import (
    CreateGameData,
    GameTypeInactiveError,
    GameTypeNotFoundError,
    GameView,
    ScheduledAtNotInFutureError, create_game_handler,
)
from lotto.main import create_sub_app
from lotto.routers import api_v1
from lotto.routers.api_v1 import router

app = create_sub_app(title="API", routers=[router])
prefix = "/v1"

database = MagicMock()
app.dependency_overrides[get_database] = lambda: database

ADMIN_HEADERS = {"X-User-Role": "admin"}
GAME_TYPE_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def make_game_view(**overrides: object) -> GameView:
    fields: dict = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "name": "6 z 49 #1",
        "game_type_id": uuid.UUID(GAME_TYPE_ID),
        "ticket_price": 10,
        "jackpot": 1000,
        "status": GameStatus.SCHEDULED,
        "scheduled_at": datetime(2026, 12, 1, 18, 0, tzinfo=UTC),
        "started_at": None,
        "finished_at": None,
        "seed_hash": "hash",
        "seed": None,
        "winning_numbers": None,
    }
    fields.update(overrides)
    return GameView(**fields)


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(return_value=make_game_view())
    monkeypatch.setattr(api_v1, "create_game_handler", mock)
    yield mock


def make_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "game_type_id": GAME_TYPE_ID,
        "scheduled_at": "2026-12-01T18:00:00Z",
    }
    body.update(overrides)
    return body


async def test_create_game_returns_created_game(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    expected = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "6 z 49 #1",
        "game_type_id": GAME_TYPE_ID,
        "ticket_price": 10,
        "jackpot": 1000,
        "status": "scheduled",
        "scheduled_at": "2026-12-01T18:00:00Z",
        "started_at": None,
        "finished_at": None,
        "seed_hash": "hash",
        "seed": None,
        "winning_numbers": None,
    }

    response = await client.post(
        f"{prefix}/games", json=make_body(), headers=ADMIN_HEADERS
    )

    assert (response.status_code, response.json()) == (201, expected)


async def test_create_game_passes_body_to_handler(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    body = make_body(name="Mikołajki", ticket_price=0, jackpot=5000)
    expected = [
        call(
            database,
            CreateGameData(
                game_type_id=uuid.UUID(GAME_TYPE_ID),
                scheduled_at=datetime(2026, 12, 1, 18, 0, tzinfo=UTC),
                name="Mikołajki",
                ticket_price=0,
                jackpot=5000,
            ),
        )
    ]

    await client.post(f"{prefix}/games", json=body, headers=ADMIN_HEADERS)

    assert handler.await_args_list == expected


async def test_create_game_leaves_optional_fields_empty(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    await client.post(f"{prefix}/games", json=make_body(), headers=ADMIN_HEADERS)

    data = handler.await_args_list[0].args[1]
    assert (data.name, data.ticket_price, data.jackpot) == (None, None, None)


@pytest.mark.parametrize("headers", [{}, {"X-User-Role": "player"}])
async def test_create_game_forbids_non_admins(
    client: httpx.AsyncClient, handler: AsyncMock, headers: dict[str, str]
) -> None:
    response = await client.post(f"{prefix}/games", json=make_body(), headers=headers)

    assert (response.status_code, handler.await_count) == (403, 0)


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (GameTypeNotFoundError, 404),
        (GameTypeInactiveError, 422),
        (ScheduledAtNotInFutureError, 422),
    ],
)
async def test_create_game_maps_handler_errors(
    client: httpx.AsyncClient,
    handler: AsyncMock,
    error: type[Exception],
    status_code: int,
) -> None:
    handler.side_effect = error

    response = await client.post(
        f"{prefix}/games", json=make_body(), headers=ADMIN_HEADERS
    )

    assert response.status_code == status_code


@pytest.mark.parametrize(
    "overrides",
    [
        {"ticket_price": -1},
        {"jackpot": -1},
        {"name": ""},
        {"scheduled_at": "2026-12-01T18:00:00"},
        {"game_type_id": "not-a-uuid"},
    ],
)
async def test_create_game_rejects_invalid_body(
    client: httpx.AsyncClient, handler: AsyncMock, overrides: dict[str, Any]
) -> None:
    response = await client.post(
        f"{prefix}/games", json=make_body(**overrides), headers=ADMIN_HEADERS
    )

    assert (response.status_code, handler.await_count) == (422, 0)


@pytest.mark.parametrize("field", ["game_type_id", "scheduled_at"])
async def test_create_game_requires_field(
    client: httpx.AsyncClient, handler: AsyncMock, field: str
) -> None:
    body = make_body()
    del body[field]

    response = await client.post(f"{prefix}/games", json=body, headers=ADMIN_HEADERS)

    assert (response.status_code, handler.await_count) == (422, 0)
