import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from admin.connectors import (
    get_auth_client,
    get_betting_client,
    get_database,
    get_lotto_client,
)
from admin.connectors.models import AdminActionType, ReportType, TargetType
from admin.connectors.services import ServiceError
from admin.handlers.handlers_v1 import (
    AdminActionsPage,
    AdminActionView,
    DailySummaryRowView,
    GameStatsRowView,
    InvalidReportPeriodError,
    ReportDetailsView,
    ReportRowView,
    UserActivityRowView,
)
from admin.main import create_sub_app
from admin.routers import api_v1
from admin.routers.api_v1 import router

app = create_sub_app(title="API", routers=[router])
prefix = "/v1"

database = MagicMock()
lotto = MagicMock()
betting = MagicMock()
auth = MagicMock()
app.dependency_overrides[get_database] = lambda: database
app.dependency_overrides[get_lotto_client] = lambda: lotto
app.dependency_overrides[get_betting_client] = lambda: betting
app.dependency_overrides[get_auth_client] = lambda: auth

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


REPORT_ID = "55555555-5555-5555-5555-555555555555"
REPORT_BODY = {
    "type": "daily_summary",
    "period_from": "2026-11-01",
    "period_to": "2026-11-30",
}


def make_report_details_view(
    report_type: ReportType, rows: list[ReportRowView]
) -> ReportDetailsView:
    return ReportDetailsView(
        id=uuid.UUID(REPORT_ID),
        type=report_type,
        period_from=date(2026, 11, 1),
        period_to=date(2026, 11, 30),
        created_by=uuid.UUID(ADMIN_ID),
        created_at=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        rows=rows,
    )


REPORT_JSON = {
    "id": REPORT_ID,
    "period_from": "2026-11-01",
    "period_to": "2026-11-30",
    "created_by": ADMIN_ID,
    "created_at": "2026-11-19T12:00:00Z",
}


@pytest.fixture
def create_report_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    mock = AsyncMock(
        return_value=make_report_details_view(ReportType.DAILY_SUMMARY, [])
    )
    monkeypatch.setattr(api_v1, "create_report_handler", mock)
    yield mock


@pytest.mark.parametrize(
    ("report_type", "row", "row_json"),
    [
        (
            ReportType.DAILY_SUMMARY,
            DailySummaryRowView(
                day=date(2026, 11, 1),
                games_played=4,
                active_players=3,
                points_spent=240,
                points_awarded=100,
            ),
            {
                "day": "2026-11-01",
                "games_played": 4,
                "active_players": 3,
                "points_spent": 240,
                "points_awarded": 100,
            },
        ),
        (
            ReportType.GAME_STATS,
            GameStatsRowView(
                game_type_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                games_played=8,
                coupons_sold=50,
                points_spent=500,
                points_awarded=200,
            ),
            {
                "game_type_id": "22222222-2222-2222-2222-222222222222",
                "games_played": 8,
                "coupons_sold": 50,
                "points_spent": 500,
                "points_awarded": 200,
            },
        ),
        (
            ReportType.USER_ACTIVITY,
            UserActivityRowView(
                user_id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
                coupons_bought=30,
                points_spent=300,
                points_won=150,
                last_seen_at=None,
            ),
            {
                "user_id": "66666666-6666-6666-6666-666666666666",
                "coupons_bought": 30,
                "points_spent": 300,
                "points_won": 150,
                "last_seen_at": None,
            },
        ),
    ],
)
async def test_create_report_returns_report_with_rows(
    client: httpx.AsyncClient,
    create_report_handler: AsyncMock,
    report_type: ReportType,
    row: ReportRowView,
    row_json: dict,
) -> None:
    create_report_handler.return_value = make_report_details_view(report_type, [row])
    expected = {**REPORT_JSON, "type": str(report_type), "rows": [row_json]}

    response = await client.post(
        f"{prefix}/reports", json={**REPORT_BODY, "type": str(report_type)}
    )

    assert (response.status_code, response.json()) == (201, expected)


async def test_create_report_passes_body_and_admin_to_handler(
    client: httpx.AsyncClient, create_report_handler: AsyncMock
) -> None:
    expected = [
        call(
            database,
            lotto,
            betting,
            auth,
            admin_id=uuid.UUID(ADMIN_ID),
            report_type=ReportType.DAILY_SUMMARY,
            period_from=date(2026, 11, 1),
            period_to=date(2026, 11, 30),
        )
    ]

    await client.post(f"{prefix}/reports", json=REPORT_BODY)

    assert create_report_handler.await_args_list == expected


@pytest.mark.parametrize(
    "body",
    [
        {**REPORT_BODY, "type": "monthly_summary"},
        {**REPORT_BODY, "period_from": "yesterday"},
        {"type": "daily_summary", "period_from": "2026-11-01"},
        {},
    ],
)
async def test_create_report_rejects_invalid_body(
    client: httpx.AsyncClient, create_report_handler: AsyncMock, body: dict
) -> None:
    response = await client.post(f"{prefix}/reports", json=body)

    assert (response.status_code, create_report_handler.await_count) == (422, 0)


async def test_create_report_returns_422_for_invalid_period(
    client: httpx.AsyncClient, create_report_handler: AsyncMock
) -> None:
    create_report_handler.side_effect = InvalidReportPeriodError(
        "period_from is after period_to."
    )

    response = await client.post(f"{prefix}/reports", json=REPORT_BODY)

    assert (response.status_code, response.json()) == (
        422,
        {"detail": "period_from is after period_to."},
    )


async def test_create_report_returns_502_when_a_service_fails(
    client: httpx.AsyncClient, create_report_handler: AsyncMock
) -> None:
    create_report_handler.side_effect = ServiceError("betting is down")

    response = await client.post(f"{prefix}/reports", json=REPORT_BODY)

    assert (response.status_code, response.json()) == (
        502,
        {"detail": "Another service failed."},
    )


async def test_create_report_requires_admin(
    client: httpx.AsyncClient, create_report_handler: AsyncMock
) -> None:
    response = await client.post(
        f"{prefix}/reports",
        json=REPORT_BODY,
        headers={"X-User-Roles": "player"},
    )

    assert (response.status_code, create_report_handler.await_count) == (403, 0)
