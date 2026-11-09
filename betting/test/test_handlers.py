import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, call

import pytest

from betting.connectors.models import Coupon, CouponStatus
from betting.exceptions import InvalidDateRange
from betting.handlers.handlers_v1 import (
    CouponResponse,
    CouponsPageResponse,
    list_coupons_handler,
)

from .factories import make_coupon

CALLER_ID = uuid.UUID(int=1)
OTHER_USER_ID = uuid.UUID(int=2)


def make_database(coupons: list[Coupon]) -> AsyncMock:
    database = AsyncMock()
    database.list_coupons.return_value = coupons
    return database


def expected_response(coupon: Coupon) -> CouponResponse:
    return CouponResponse(
        id=coupon.id,
        created_at=coupon.created_at,
        game_id=coupon.game_id,
        game_type_id=coupon.game_type_id,
        numbers=coupon.numbers,
        is_quick_pick=coupon.is_quick_pick,
        price=coupon.price,
        status=coupon.status,
        hits=coupon.hits,
        points_won=coupon.points_won,
    )


async def test_list_coupons_passes_filters_to_database() -> None:
    database = make_database([])
    game_type_id = uuid.uuid4()
    created_from = datetime(2026, 11, 1, tzinfo=UTC)
    created_to = datetime(2026, 11, 30, tzinfo=UTC)
    expected = [
        call(
            user_id=CALLER_ID,
            game_type_id=game_type_id,
            status=CouponStatus.WON,
            created_from=created_from,
            created_to=created_to,
            include_active=True,
            limit=10,
            offset=20,
        )
    ]

    await list_coupons_handler(
        database,
        caller_id=CALLER_ID,
        user_id=CALLER_ID,
        game_type_id=game_type_id,
        status=CouponStatus.WON,
        created_from=created_from,
        created_to=created_to,
        limit=10,
        offset=20,
    )

    assert database.list_coupons.await_args_list == expected


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        (None, {"user_id": CALLER_ID, "include_active": True}),
        (CALLER_ID, {"user_id": CALLER_ID, "include_active": True}),
        (OTHER_USER_ID, {"user_id": OTHER_USER_ID, "include_active": False}),
    ],
)
async def test_list_coupons_shows_active_coupons_only_to_owner(
    user_id: uuid.UUID | None, expected: dict
) -> None:
    database = make_database([])

    await list_coupons_handler(
        database, CALLER_ID, user_id, None, None, None, None, 50, 0
    )

    kwargs = database.list_coupons.await_args.kwargs
    assert {key: kwargs[key] for key in expected} == expected


async def test_list_coupons_rejects_from_after_to() -> None:
    created_from = datetime(2026, 12, 1, tzinfo=UTC)
    created_to = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(InvalidDateRange):
        await list_coupons_handler(
            make_database([]),
            CALLER_ID,
            None,
            None,
            None,
            created_from,
            created_to,
            50,
            0,
        )


async def test_list_coupons_returns_coupons() -> None:
    coupons = [
        make_coupon(),
        make_coupon(status=CouponStatus.ACTIVE, hits=None, points_won=None),
    ]
    expected = CouponsPageResponse(
        items=[expected_response(coupon) for coupon in coupons]
    )

    page = await list_coupons_handler(
        make_database(coupons), CALLER_ID, None, None, None, None, None, 50, 0
    )

    assert page == expected


async def test_list_coupons_returns_empty_page() -> None:
    page = await list_coupons_handler(
        make_database([]), CALLER_ID, None, None, None, None, None, 50, 0
    )

    assert page == CouponsPageResponse(items=[])
