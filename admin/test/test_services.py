from datetime import date

import pytest

from admin.connectors.services import (
    FAKE_USER_IDS,
    AuthClient,
    BettingClient,
    CouponCount,
    LottoClient,
    UserStatus,
    WalletClient,
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


@pytest.mark.parametrize(
    ("status", "expected_ids", "expected_total"),
    [
        (UserStatus.ALL, [FAKE_USER_IDS[1], FAKE_USER_IDS[2]], 3),
        (UserStatus.ONLINE, [], 1),
        (UserStatus.OFFLINE, [FAKE_USER_IDS[2]], 2),
    ],
)
async def test_list_users_filters_by_status_and_paginates(
    status: UserStatus, expected_ids: list, expected_total: int
) -> None:
    users, total = await AuthClient().list_users(status, limit=2, offset=1)

    assert ([user.id for user in users], total) == (expected_ids, expected_total)


async def test_get_wallets_returns_only_requested_wallets() -> None:
    wallets = await WalletClient().get_wallets([FAKE_USER_IDS[0]])

    assert [wallet.user_id for wallet in wallets] == [FAKE_USER_IDS[0]]


async def test_coupon_counts_gives_zero_to_users_without_coupons() -> None:
    counts = await BettingClient().coupon_counts([FAKE_USER_IDS[2], FAKE_USER_IDS[0]])

    assert counts == [
        CouponCount(user_id=FAKE_USER_IDS[2], coupons_count=0),
        CouponCount(user_id=FAKE_USER_IDS[0], coupons_count=42),
    ]
