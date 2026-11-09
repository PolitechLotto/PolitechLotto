import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, call

import pytest

from betting.connectors.lotto import LottoGame, LottoGameType
from betting.connectors.models import Coupon, CouponStatus
from betting.exceptions import (
    GameNotFound,
    GameNotOpen,
    InsufficientFunds,
    InvalidDateRange,
    InvalidNumbers,
    UpstreamError,
)
from betting.handlers import handlers_v1
from betting.handlers.handlers_v1 import (
    CouponResponse,
    CouponsPageResponse,
    create_coupon_handler,
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


GAME_ID = uuid.UUID(int=10)
GAME_TYPE_ID = uuid.UUID(int=11)
COUPON_ID = uuid.UUID(int=12)
NUMBERS = [41, 3, 22, 48, 7, 19]


def make_game(**overrides: Any) -> LottoGame:
    fields: dict[str, Any] = {
        "id": GAME_ID,
        "game_type_id": GAME_TYPE_ID,
        "ticket_price": 10,
        "status": "scheduled",
        "scheduled_at": datetime.now(UTC) + timedelta(days=1),
        "started_at": None,
        "game_type": LottoGameType(
            id=GAME_TYPE_ID, number_pool_size=49, number_pick_count=6
        ),
    }
    fields.update(overrides)
    return LottoGame(**fields)


def make_lotto(game: LottoGame | None = None) -> AsyncMock:
    lotto = AsyncMock()
    lotto.get_game.return_value = game or make_game()
    return lotto


def make_saving_database(coupon: Coupon | None = None) -> AsyncMock:
    database = AsyncMock()
    database.create_coupon.return_value = coupon or make_coupon(id=COUPON_ID)
    return database


@pytest.fixture
def coupon_id(monkeypatch: pytest.MonkeyPatch) -> uuid.UUID:
    monkeypatch.setattr(handlers_v1.uuid, "uuid4", lambda: COUPON_ID)
    return COUPON_ID


async def test_create_coupon_charges_ticket_price_and_saves_coupon(
    coupon_id: uuid.UUID,
) -> None:
    database, lotto, wallet = make_saving_database(), make_lotto(), AsyncMock()
    expected = (
        [call(GAME_ID)],
        [call(CALLER_ID, amount=10, reference_id=coupon_id)],
        [
            call(
                id=coupon_id,
                user_id=CALLER_ID,
                game_id=GAME_ID,
                game_type_id=GAME_TYPE_ID,
                numbers=NUMBERS,
                is_quick_pick=False,
                price=10,
            )
        ],
    )

    await create_coupon_handler(database, lotto, wallet, CALLER_ID, GAME_ID, NUMBERS)

    assert (
        lotto.get_game.await_args_list,
        wallet.charge.await_args_list,
        database.create_coupon.await_args_list,
    ) == expected


async def test_create_coupon_returns_saved_coupon() -> None:
    coupon = make_coupon(status=CouponStatus.ACTIVE, hits=None, points_won=None)

    response = await create_coupon_handler(
        make_saving_database(coupon),
        make_lotto(),
        AsyncMock(),
        CALLER_ID,
        GAME_ID,
        NUMBERS,
    )

    assert response == expected_response(coupon)


async def test_create_coupon_generates_quick_pick_numbers() -> None:
    database = make_saving_database()
    expected = {"count": 6, "unique": 6, "in_range": True, "is_quick_pick": True}

    await create_coupon_handler(
        database, make_lotto(), AsyncMock(), CALLER_ID, GAME_ID, None
    )

    kwargs = database.create_coupon.await_args.kwargs
    numbers = kwargs["numbers"]
    assert {
        "count": len(numbers),
        "unique": len(set(numbers)),
        "in_range": all(1 <= number <= 49 for number in numbers),
        "is_quick_pick": kwargs["is_quick_pick"],
    } == expected


@pytest.mark.parametrize(
    "game",
    [
        make_game(status="finished"),
        make_game(status="cancelled"),
        make_game(started_at=datetime(2026, 11, 1, tzinfo=UTC)),
        make_game(scheduled_at=datetime(2026, 11, 1, tzinfo=UTC)),
    ],
    ids=["finished", "cancelled", "started", "scheduled-in-past"],
)
async def test_create_coupon_rejects_game_that_is_not_open(game: LottoGame) -> None:
    with pytest.raises(GameNotOpen):
        await create_coupon_handler(
            make_saving_database(),
            make_lotto(game),
            AsyncMock(),
            CALLER_ID,
            GAME_ID,
            NUMBERS,
        )


@pytest.mark.parametrize(
    ("numbers", "message"),
    [
        ([1, 2, 3, 4, 5], "Pick exactly 6 numbers."),
        ([1, 2, 3, 4, 5, 6, 7], "Pick exactly 6 numbers."),
        ([1, 1, 2, 3, 4, 5], "Numbers must be unique."),
        ([0, 1, 2, 3, 4, 5], "Numbers must be between 1 and 49."),
        ([1, 2, 3, 4, 5, 50], "Numbers must be between 1 and 49."),
    ],
)
async def test_create_coupon_rejects_invalid_numbers(
    numbers: list[int], message: str
) -> None:
    with pytest.raises(InvalidNumbers, match=f"^{message}$"):
        await create_coupon_handler(
            make_saving_database(),
            make_lotto(),
            AsyncMock(),
            CALLER_ID,
            GAME_ID,
            numbers,
        )


async def test_create_coupon_does_not_charge_for_invalid_numbers() -> None:
    wallet = AsyncMock()

    with pytest.raises(InvalidNumbers):
        await create_coupon_handler(
            make_saving_database(), make_lotto(), wallet, CALLER_ID, GAME_ID, [1]
        )

    assert wallet.charge.await_count == 0


@pytest.mark.parametrize("error", [InsufficientFunds(), UpstreamError("wallet")])
async def test_create_coupon_does_not_save_coupon_when_charge_fails(
    error: Exception,
) -> None:
    database, wallet = make_saving_database(), AsyncMock()
    wallet.charge.side_effect = error

    with pytest.raises(type(error)):
        await create_coupon_handler(
            database, make_lotto(), wallet, CALLER_ID, GAME_ID, NUMBERS
        )

    assert database.create_coupon.await_count == 0


@pytest.mark.parametrize("error", [GameNotFound(), UpstreamError("lotto")])
async def test_create_coupon_does_not_charge_when_game_lookup_fails(
    error: Exception,
) -> None:
    lotto, wallet = make_lotto(), AsyncMock()
    lotto.get_game.side_effect = error

    with pytest.raises(type(error)):
        await create_coupon_handler(
            make_saving_database(), lotto, wallet, CALLER_ID, GAME_ID, NUMBERS
        )

    assert wallet.charge.await_count == 0
