from datetime import date

import pytest

from admin.connectors.services import (
    FAKE_USER_IDS,
    AuthClient,
    BettingClient,
    LottoClient,
)


@pytest.mark.parametrize(
    ("period_to", "expected"),
    [
        (date(2026, 11, 1), [date(2026, 11, 1)]),
        (date(2026, 11, 30), [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)]),
    ],
)
async def test_daily_statistics_stay_inside_the_period(
    period_to: date, expected: list[date]
) -> None:
    period_from = date(2026, 11, 1)

    games = await LottoClient().games_by_day(period_from, period_to)
    coupons = await BettingClient().coupon_stats_by_day(period_from, period_to)

    assert ([row.day for row in games], [row.day for row in coupons]) == (
        expected,
        expected,
    )


async def test_get_users_returns_only_requested_users() -> None:
    users = await AuthClient().get_users([FAKE_USER_IDS[1]])

    assert [user.id for user in users] == [FAKE_USER_IDS[1]]
