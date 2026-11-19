"""Clients of the other PolitechLotto services.

The endpoints they call do not exist yet, so every client returns a small static data set shaped
like the ticket that defines the endpoint. When an endpoint is ready, replace the body of its
method with an HTTP call, and raise `ServiceError` when the service fails or does not answer.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


class ServiceError(Exception):
    """Another service failed or did not answer."""


FAKE_GAME_TYPE_IDS = (
    uuid.UUID("a0000000-0000-0000-0000-000000000001"),
    uuid.UUID("a0000000-0000-0000-0000-000000000002"),
)
FAKE_USER_IDS = (
    uuid.UUID("b0000000-0000-0000-0000-000000000001"),
    uuid.UUID("b0000000-0000-0000-0000-000000000002"),
    uuid.UUID("b0000000-0000-0000-0000-000000000003"),
)


def _first_days(period_from: date, period_to: date, count: int = 3) -> list[date]:
    days = (period_from + timedelta(days=offset) for offset in range(count))
    return [day for day in days if day <= period_to]


@dataclass(frozen=True)
class GamesPlayedByDay:
    day: date
    games_played: int


@dataclass(frozen=True)
class GamesPlayedByGameType:
    game_type_id: uuid.UUID
    games_played: int


class LottoClient:
    """lotto `GET /api/lotto/v1/statistics/games` (POL-90)."""

    async def games_by_day(
        self, period_from: date, period_to: date
    ) -> list[GamesPlayedByDay]:
        return [
            GamesPlayedByDay(day=day, games_played=4)
            for day in _first_days(period_from, period_to)
        ]

    async def games_by_game_type(
        self, period_from: date, period_to: date
    ) -> list[GamesPlayedByGameType]:
        return [
            GamesPlayedByGameType(game_type_id=FAKE_GAME_TYPE_IDS[0], games_played=8),
            GamesPlayedByGameType(game_type_id=FAKE_GAME_TYPE_IDS[1], games_played=4),
        ]


@dataclass(frozen=True)
class CouponStatsByDay:
    day: date
    coupons_sold: int
    points_spent: int
    points_awarded: int
    active_players: int


@dataclass(frozen=True)
class CouponStatsByGameType:
    game_type_id: uuid.UUID
    coupons_sold: int
    points_spent: int
    points_awarded: int


@dataclass(frozen=True)
class CouponStatsByUser:
    user_id: uuid.UUID
    coupons_sold: int
    points_spent: int
    points_awarded: int


class BettingClient:
    """betting `GET /api/betting/v1/statistics` (POL-108)."""

    async def coupon_stats_by_day(
        self, period_from: date, period_to: date
    ) -> list[CouponStatsByDay]:
        return [
            CouponStatsByDay(
                day=day,
                coupons_sold=24,
                points_spent=240,
                points_awarded=100,
                active_players=3,
            )
            for day in _first_days(period_from, period_to)
        ]

    async def coupon_stats_by_game_type(
        self, period_from: date, period_to: date
    ) -> list[CouponStatsByGameType]:
        return [
            CouponStatsByGameType(
                game_type_id=FAKE_GAME_TYPE_IDS[0],
                coupons_sold=50,
                points_spent=500,
                points_awarded=200,
            ),
            CouponStatsByGameType(
                game_type_id=FAKE_GAME_TYPE_IDS[1],
                coupons_sold=22,
                points_spent=220,
                points_awarded=100,
            ),
        ]

    async def coupon_stats_by_user(
        self, period_from: date, period_to: date
    ) -> list[CouponStatsByUser]:
        return [
            CouponStatsByUser(
                user_id=FAKE_USER_IDS[0],
                coupons_sold=30,
                points_spent=300,
                points_awarded=150,
            ),
            CouponStatsByUser(
                user_id=FAKE_USER_IDS[1],
                coupons_sold=12,
                points_spent=120,
                points_awarded=0,
            ),
        ]


@dataclass(frozen=True)
class AuthUser:
    id: uuid.UUID
    username: str
    email: str
    role: str
    created_at: datetime
    last_login_at: datetime | None
    last_seen_at: datetime | None
    is_online: bool


FAKE_USERS = (
    AuthUser(
        id=FAKE_USER_IDS[0],
        username="szczesciarz",
        email="szczesciarz@example.com",
        role="player",
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        last_login_at=datetime(2026, 11, 18, 19, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 11, 18, 19, 45, tzinfo=UTC),
        is_online=True,
    ),
    AuthUser(
        id=FAKE_USER_IDS[1],
        username="typer",
        email="typer@example.com",
        role="player",
        created_at=datetime(2026, 10, 5, 8, 30, tzinfo=UTC),
        last_login_at=datetime(2026, 11, 10, 7, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 11, 10, 7, 20, tzinfo=UTC),
        is_online=False,
    ),
    AuthUser(
        id=FAKE_USER_IDS[2],
        username="nowy_gracz",
        email="nowy_gracz@example.com",
        role="player",
        created_at=datetime(2026, 11, 15, 16, 0, tzinfo=UTC),
        last_login_at=None,
        last_seen_at=None,
        is_online=False,
    ),
)


class AuthClient:
    """auth users, as in `GET /api/auth/v1/users` (POL-74)."""

    async def get_users(self, user_ids: list[uuid.UUID]) -> list[AuthUser]:
        """Users with the given IDs. Auth has no ticket for this lookup yet."""
        wanted = set(user_ids)
        return [user for user in FAKE_USERS if user.id in wanted]
