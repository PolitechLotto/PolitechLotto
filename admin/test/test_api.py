import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from admin.connectors import get_database
from admin.connectors.models import AdminActionType, TargetType
from admin.handlers.handlers_v1 import AdminActionsPage, AdminActionView
from admin.main import create_sub_app
from admin.routers import api_v1
from admin.routers.api_v1 import router

app = create_sub_app(title="API", routers=[router])
prefix = "/v1"

database = MagicMock()
app.dependency_overrides[get_database] = lambda: database

ADMIN_ID = "33333333-3333-3333-3333-333333333333"
ADMIN_HEADERS = {"X-User-Id": ADMIN_ID, "X-User-Roles": "player,admin"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers=ADMIN_HEADERS,
    ) as client:
        yield client


@pytest.fixture
def actions_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(return_value=AdminActionsPage(items=[], total=0))
    monkeypatch.setattr(api_v1, "list_admin_actions_handler", mock)
    yield mock


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-User-Roles": "admin"},
        {"X-User-Id": "not-a-uuid", "X-User-Roles": "admin"},
    ],
)
async def test_rejects_request_without_identity(
    client: httpx.AsyncClient, actions_handler: AsyncMock, headers: dict
) -> None:
    client.headers.clear()

    response = await client.get(f"{prefix}/actions", headers=headers)

    assert (response.status_code, response.json(), actions_handler.await_count) == (
        401,
        {"detail": "Not authenticated."},
        0,
    )


@pytest.mark.parametrize("roles", [None, "", "player", "player, moderator", "admins"])
async def test_rejects_caller_without_admin_role(
    client: httpx.AsyncClient, actions_handler: AsyncMock, roles: str | None
) -> None:
    client.headers.clear()
    headers = {"X-User-Id": ADMIN_ID}
    if roles is not None:
        headers["X-User-Roles"] = roles

    response = await client.get(f"{prefix}/actions", headers=headers)

    assert (response.status_code, response.json(), actions_handler.await_count) == (
        403,
        {"detail": "Admin role required."},
        0,
    )


async def test_accepts_admin_role_with_spaces(
    client: httpx.AsyncClient, actions_handler: AsyncMock
) -> None:
    response = await client.get(
        f"{prefix}/actions",
        headers={"X-User-Id": ADMIN_ID, "X-User-Roles": "player , admin"},
    )

    assert response.status_code == 200


async def test_list_admin_actions_returns_paginated_actions(
    client: httpx.AsyncClient, actions_handler: AsyncMock
) -> None:
    actions_handler.return_value = AdminActionsPage(
        items=[
            AdminActionView(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                admin_id=uuid.UUID(ADMIN_ID),
                action=AdminActionType.GAME_CANCELLED,
                target_type=TargetType.GAME,
                target_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                description="Cancelled game 6 z 49.",
                created_at=datetime(2026, 11, 1, 18, 0, tzinfo=UTC),
            )
        ],
        total=3,
    )
    expected = {
        "items": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "admin_id": ADMIN_ID,
                "action": "game_cancelled",
                "target_type": "game",
                "target_id": "22222222-2222-2222-2222-222222222222",
                "description": "Cancelled game 6 z 49.",
                "created_at": "2026-11-01T18:00:00Z",
            }
        ],
        "total": 3,
    }

    response = await client.get(f"{prefix}/actions")

    assert (response.status_code, response.json()) == (200, expected)


async def test_list_admin_actions_uses_default_query(
    client: httpx.AsyncClient, actions_handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            action=None,
            target_type=None,
            admin_id=None,
            created_from=None,
            created_to=None,
            limit=50,
            offset=0,
        )
    ]

    await client.get(f"{prefix}/actions")

    assert actions_handler.await_args_list == expected


async def test_list_admin_actions_passes_query_to_handler(
    client: httpx.AsyncClient, actions_handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            action=AdminActionType.POINTS_ADJUSTED,
            target_type=TargetType.WALLET,
            admin_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            created_from=datetime(2026, 11, 1, tzinfo=UTC),
            created_to=datetime(2026, 11, 29, 23, 0, tzinfo=UTC),
            limit=200,
            offset=20,
        )
    ]

    await client.get(
        f"{prefix}/actions",
        params={
            "action": "points_adjusted",
            "target_type": "wallet",
            "admin_id": "44444444-4444-4444-4444-444444444444",
            "from": "2026-11-01T00:00:00Z",
            "to": "2026-11-30T00:00:00+01:00",
            "limit": 200,
            "offset": 20,
        },
    )

    assert actions_handler.await_args_list == expected


@pytest.mark.parametrize(
    "params",
    [
        {"action": "user_created"},
        {"target_type": "coupon"},
        {"admin_id": "not-a-uuid"},
        {"from": "yesterday"},
        {"to": "2026-11-01T00:00:00"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ],
)
async def test_list_admin_actions_rejects_invalid_query(
    client: httpx.AsyncClient, actions_handler: AsyncMock, params: dict
) -> None:
    response = await client.get(f"{prefix}/actions", params=params)

    assert (response.status_code, actions_handler.await_count) == (422, 0)
