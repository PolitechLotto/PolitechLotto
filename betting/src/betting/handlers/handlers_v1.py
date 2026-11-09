import secrets
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from betting.connectors.db import Database
from betting.connectors.lotto import LottoClient, LottoGame
from betting.connectors.models import CouponStatus
from betting.connectors.wallet import WalletClient
from betting.exceptions import GameNotOpen, InvalidDateRange, InvalidNumbers

SCHEDULED = "scheduled"

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
