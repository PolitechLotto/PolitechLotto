import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from betting.connectors.db import Database
from betting.connectors.models import CouponStatus
from betting.exceptions import InvalidDateRange


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
