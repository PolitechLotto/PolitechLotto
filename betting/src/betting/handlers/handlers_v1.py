import secrets
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from betting.connectors.db import Database
from betting.connectors.lotto import LottoClient, LottoGame
from betting.connectors.models import Coupon, CouponStatus
from betting.connectors.wallet import WalletClient
from betting.exceptions import (
    CouponNotFound,
    GameNotOpen,
    InvalidDateRange,
    InvalidNumbers,
)

SCHEDULED = "scheduled"
ADMIN_ROLE = "admin"

_random = secrets.SystemRandom()


class CouponResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    game_id: uuid.UUID
    game_type_id: uuid.UUID
    numbers: list[int]
    is_quick_pick: bool
    price: int
    status: CouponStatus
    hits: int | None
    points_won: int | None


class CouponsPageResponse(BaseModel):
    items: list[CouponResponse]


class GameCouponResponse(BaseModel):
    """A coupon as other players see it, in a game's coupon table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    user_id: uuid.UUID
    numbers: list[int] | None
    is_quick_pick: bool
    status: CouponStatus
    hits: int | None
    points_won: int | None


class GameCouponsPageResponse(BaseModel):
    items: list[GameCouponResponse]


class CouponCountResponse(BaseModel):
    user_id: uuid.UUID
    coupons_count: int


def _to_game_coupon_response(coupon: Coupon) -> GameCouponResponse:
    response = GameCouponResponse.model_validate(coupon)
    # Numbers stay hidden until the game is drawn, so they cannot be copied.
    if coupon.status == CouponStatus.ACTIVE:
        return response.model_copy(update={"numbers": None})
    return response


async def list_coupons_handler(
    database: Database,
    caller_id: uuid.UUID,
    user_id: uuid.UUID | None,
    game_type_id: uuid.UUID | None,
    status: CouponStatus | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    offset: int,
) -> CouponsPageResponse:
    if created_from and created_to and created_from > created_to:
        raise InvalidDateRange
    user_id = user_id or caller_id
    coupons = await database.list_coupons(
        user_id=user_id,
        game_type_id=game_type_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        include_active=user_id == caller_id,
        limit=limit,
        offset=offset,
    )
    return CouponsPageResponse(
        items=[CouponResponse.model_validate(coupon) for coupon in coupons]
    )


async def list_game_coupons_handler(
    database: Database,
    game_id: uuid.UUID,
    status: CouponStatus | None,
    limit: int,
    offset: int,
) -> GameCouponsPageResponse:
    coupons = await database.list_coupons_for_game(
        game_id=game_id, status=status, limit=limit, offset=offset
    )
    return GameCouponsPageResponse(
        items=[_to_game_coupon_response(coupon) for coupon in coupons]
    )


async def count_coupons_handler(
    database: Database, user_ids: list[uuid.UUID]
) -> list[CouponCountResponse]:
    """Counts each user's coupons, in the order asked. Users without coupons get 0."""
    unique_ids = list(dict.fromkeys(user_ids))
    counts = await database.count_coupons_by_users(unique_ids)
    return [
        CouponCountResponse(user_id=user_id, coupons_count=counts.get(user_id, 0))
        for user_id in unique_ids
    ]


async def get_coupon_handler(
    database: Database,
    caller_id: uuid.UUID,
    caller_role: str | None,
    coupon_id: uuid.UUID,
) -> CouponResponse:
    coupon = await database.get_coupon(coupon_id)
    # Another player's coupon looks the same as a missing one: do not reveal it exists.
    if coupon is None or (coupon.user_id != caller_id and caller_role != ADMIN_ROLE):
        raise CouponNotFound
    return CouponResponse.model_validate(coupon)


async def create_coupon_handler(
    database: Database,
    lotto: LottoClient,
    wallet: WalletClient,
    user_id: uuid.UUID,
    game_id: uuid.UUID,
    numbers: list[int] | None,
) -> CouponResponse:
    """Buys a coupon. `numbers=None` means quick pick."""
    game = await lotto.get_game(game_id)
    _check_game_is_open(game)
    pool_size = game.game_type.number_pool_size
    pick_count = game.game_type.number_pick_count
    if numbers is None:
        numbers = _random.sample(range(1, pool_size + 1), pick_count)
        is_quick_pick = True
    else:
        _check_numbers(numbers, pool_size, pick_count)
        is_quick_pick = False

    # The ID comes first so the wallet charge can reference it (and be retried).
    coupon_id = uuid.uuid4()
    await wallet.charge(user_id, amount=game.ticket_price, reference_id=coupon_id)
    coupon = await database.create_coupon(
        id=coupon_id,
        user_id=user_id,
        game_id=game.id,
        game_type_id=game.game_type_id,
        numbers=numbers,
        is_quick_pick=is_quick_pick,
        price=game.ticket_price,
    )
    return CouponResponse.model_validate(coupon)


def _check_game_is_open(game: LottoGame) -> None:
    if (
        game.status != SCHEDULED
        or game.started_at is not None
        or game.scheduled_at <= datetime.now(UTC)
    ):
        raise GameNotOpen


def _check_numbers(numbers: list[int], pool_size: int, pick_count: int) -> None:
    if len(numbers) != pick_count:
        raise InvalidNumbers(f"Pick exactly {pick_count} numbers.")
    if len(set(numbers)) != len(numbers):
        raise InvalidNumbers("Numbers must be unique.")
    if any(number < 1 or number > pool_size for number in numbers):
        raise InvalidNumbers(f"Numbers must be between 1 and {pool_size}.")
