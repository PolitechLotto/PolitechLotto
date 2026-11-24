import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from betting.connectors import get_database, get_lotto, get_wallet
from betting.connectors.models import CouponStatus
from betting.exceptions import (
    GameNotFound,
    GameNotOpen,
    InsufficientFunds,
    InvalidDateRange,
    InvalidNumbers,
    UpstreamError,
)
from betting.handlers.handlers_v1 import CouponResponse, CouponsPageResponse
from betting.main import create_sub_app
from betting.routers import api_v1
from betting.routers.api_v1 import router

app = create_sub_app(title="API", routers=[router])
prefix = "/v1"

database = MagicMock()
lotto = MagicMock()
wallet = MagicMock()
app.dependency_overrides[get_database] = lambda: database
app.dependency_overrides[get_lotto] = lambda: lotto
app.dependency_overrides[get_wallet] = lambda: wallet

CALLER_ID = "00000000-0000-0000-0000-000000000001"
HEADERS = {"X-User-Id": CALLER_ID}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(return_value=CouponsPageResponse(items=[]))
    monkeypatch.setattr(api_v1, "list_coupons_handler", mock)
    yield mock


def make_coupon_response() -> CouponResponse:
    return CouponResponse(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        created_at=datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
        game_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        game_type_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        numbers=[1, 2, 3, 4, 5, 6],
        is_quick_pick=True,
        price=10,
        status=CouponStatus.ACTIVE,
        hits=None,
        points_won=None,
    )


async def test_list_coupons_returns_paginated_coupons(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    handler.return_value = CouponsPageResponse(items=[make_coupon_response()])
    expected = {
        "items": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "created_at": "2026-11-01T17:00:00Z",
                "game_id": "22222222-2222-2222-2222-222222222222",
                "game_type_id": "33333333-3333-3333-3333-333333333333",
                "numbers": [1, 2, 3, 4, 5, 6],
                "is_quick_pick": True,
                "price": 10,
                "status": "active",
                "hits": None,
                "points_won": None,
            }
        ],
    }

    response = await client.get(f"{prefix}/coupons", headers=HEADERS)

    assert (response.status_code, response.json()) == (200, expected)


async def test_list_coupons_uses_default_query(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            caller_id=uuid.UUID(CALLER_ID),
            user_id=None,
            game_type_id=None,
            status=None,
            created_from=None,
            created_to=None,
            limit=50,
            offset=0,
        )
    ]

    await client.get(f"{prefix}/coupons", headers=HEADERS)

    assert handler.await_args_list == expected


async def test_list_coupons_passes_query_to_handler(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            caller_id=uuid.UUID(CALLER_ID),
            user_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            game_type_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            status=CouponStatus.LOST,
            created_from=datetime(2026, 11, 1, tzinfo=UTC),
            created_to=datetime(2026, 11, 29, 23, 0, tzinfo=UTC),
            limit=200,
            offset=20,
        )
    ]

    await client.get(
        f"{prefix}/coupons",
        headers=HEADERS,
        params={
            "user_id": "44444444-4444-4444-4444-444444444444",
            "game_type_id": "33333333-3333-3333-3333-333333333333",
            "status": "lost",
            "from": "2026-11-01T00:00:00Z",
            "to": "2026-11-30T00:00:00+01:00",
            "limit": 200,
            "offset": 20,
        },
    )

    assert handler.await_args_list == expected


@pytest.mark.parametrize(
    ("headers", "params"),
    [
        ({}, {}),
        ({"X-User-Id": "not-a-uuid"}, {}),
        (HEADERS, {"user_id": "not-a-uuid"}),
        (HEADERS, {"game_type_id": "not-a-uuid"}),
        (HEADERS, {"status": "pending"}),
        (HEADERS, {"from": "yesterday"}),
        (HEADERS, {"from": "2026-11-01T00:00:00"}),
        (HEADERS, {"limit": 0}),
        (HEADERS, {"limit": 201}),
        (HEADERS, {"offset": -1}),
    ],
)
async def test_list_coupons_rejects_invalid_request(
    client: httpx.AsyncClient, handler: AsyncMock, headers: dict, params: dict
) -> None:
    response = await client.get(f"{prefix}/coupons", headers=headers, params=params)

    assert (response.status_code, handler.await_count) == (422, 0)


async def test_list_coupons_returns_422_for_invalid_date_range(
    client: httpx.AsyncClient, handler: AsyncMock
) -> None:
    handler.side_effect = InvalidDateRange
    expected = (422, {"detail": "`from` must not be after `to`."})

    response = await client.get(f"{prefix}/coupons", headers=HEADERS)

    assert (response.status_code, response.json()) == expected


GAME_ID = "22222222-2222-2222-2222-222222222222"
NUMBERS = [41, 3, 22, 48, 7, 19]


@pytest.fixture
def create_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(return_value=make_coupon_response())
    monkeypatch.setattr(api_v1, "create_coupon_handler", mock)
    yield mock


async def test_create_coupon_returns_created_coupon(
    client: httpx.AsyncClient, create_handler: AsyncMock
) -> None:
    expected = {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-11-01T17:00:00Z",
        "game_id": GAME_ID,
        "game_type_id": "33333333-3333-3333-3333-333333333333",
        "numbers": [1, 2, 3, 4, 5, 6],
        "is_quick_pick": True,
        "price": 10,
        "status": "active",
        "hits": None,
        "points_won": None,
    }

    response = await client.post(
        f"{prefix}/coupons",
        headers=HEADERS,
        json={"game_id": GAME_ID, "is_quick_pick": True},
    )

    assert (response.status_code, response.json()) == (201, expected)


@pytest.mark.parametrize(
    ("body", "numbers"),
    [
        ({"game_id": GAME_ID, "numbers": NUMBERS}, NUMBERS),
        ({"game_id": GAME_ID, "numbers": NUMBERS, "is_quick_pick": False}, NUMBERS),
        ({"game_id": GAME_ID, "is_quick_pick": True}, None),
    ],
    ids=["numbers", "numbers-explicit-false", "quick-pick"],
)
async def test_create_coupon_passes_request_to_handler(
    client: httpx.AsyncClient, create_handler: AsyncMock, body: dict, numbers: list
) -> None:
    expected = [
        call(
            database,
            lotto,
            wallet,
            user_id=uuid.UUID(CALLER_ID),
            game_id=uuid.UUID(GAME_ID),
            numbers=numbers,
        )
    ]

    await client.post(f"{prefix}/coupons", headers=HEADERS, json=body)

    assert create_handler.await_args_list == expected


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ({}, {"game_id": GAME_ID, "is_quick_pick": True}),
        (HEADERS, {"is_quick_pick": True}),
        (HEADERS, {"game_id": "not-a-uuid", "is_quick_pick": True}),
        (HEADERS, {"game_id": GAME_ID}),
        (HEADERS, {"game_id": GAME_ID, "is_quick_pick": False}),
        (HEADERS, {"game_id": GAME_ID, "numbers": NUMBERS, "is_quick_pick": True}),
        (HEADERS, {"game_id": GAME_ID, "numbers": ["a"]}),
    ],
    ids=[
        "no-user",
        "no-game",
        "invalid-game-id",
        "neither",
        "neither-explicit-false",
        "both",
        "non-integer-numbers",
    ],
)
async def test_create_coupon_rejects_invalid_request(
    client: httpx.AsyncClient, create_handler: AsyncMock, headers: dict, body: dict
) -> None:
    response = await client.post(f"{prefix}/coupons", headers=headers, json=body)

    assert (response.status_code, create_handler.await_count) == (422, 0)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GameNotFound(), (404, {"detail": "Game not found."})),
        (InsufficientFunds(), (409, {"detail": "Not enough points."})),
        (GameNotOpen(), (422, {"detail": "The game is not open for betting."})),
        (
            InvalidNumbers("Numbers must be unique."),
            (422, {"detail": "Numbers must be unique."}),
        ),
        (UpstreamError("lotto"), (502, {"detail": "The lotto service failed."})),
        (UpstreamError("wallet"), (502, {"detail": "The wallet service failed."})),
    ],
    ids=[
        "game-not-found",
        "insufficient-funds",
        "game-not-open",
        "invalid-numbers",
        "lotto-failed",
        "wallet-failed",
    ],
)
async def test_create_coupon_maps_errors(
    client: httpx.AsyncClient,
    create_handler: AsyncMock,
    error: Exception,
    expected: tuple,
) -> None:
    create_handler.side_effect = error

    response = await client.post(
        f"{prefix}/coupons",
        headers=HEADERS,
        json={"game_id": GAME_ID, "is_quick_pick": True},
    )

    assert (response.status_code, response.json()) == expected
