import uuid
from typing import Annotated, Self

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, model_validator

from betting.connectors import get_database, get_lotto, get_wallet
from betting.connectors.db import Database
from betting.connectors.lotto import LottoClient
from betting.connectors.models import CouponStatus
from betting.connectors.wallet import WalletClient
from betting.exceptions import (
    CouponNotFound,
    GameNotFound,
    GameNotOpen,
    InsufficientFunds,
    InvalidDateRange,
    InvalidNumbers,
    UpstreamError,
)
from betting.handlers.handlers_v1 import (
    CouponCountResponse,
    CouponResponse,
    CouponsPageResponse,
    GameCouponsPageResponse,
    count_coupons_handler,
    create_coupon_handler,
    get_coupon_handler,
    list_coupons_handler,
    list_game_coupons_handler,
)

router = APIRouter(prefix="/v1")

MAX_USER_IDS = 200


class CreateCouponRequest(BaseModel):
    game_id: uuid.UUID
    numbers: list[int] | None = None
    is_quick_pick: bool = False

    @model_validator(mode="after")
    def numbers_xor_quick_pick(self) -> Self:
        if (self.numbers is None) == (not self.is_quick_pick):
            raise ValueError("Send either `numbers` or `is_quick_pick: true`.")
        return self


@router.get(
    "/coupons",
    description=(
        "Lists a player's coupons, newest first. Active coupons are shown only"
        " to their owner."
    ),
)
async def list_coupons(
    database: Annotated[Database, Depends(get_database)],
    x_user_id: Annotated[uuid.UUID, Header()],
    user_id: uuid.UUID | None = None,
    game_type_id: uuid.UUID | None = None,
    status: CouponStatus | None = None,
    created_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    created_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CouponsPageResponse:
    try:
        return await list_coupons_handler(
            database,
            caller_id=x_user_id,
            user_id=user_id,
            game_type_id=game_type_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
            offset=offset,
        )
    except InvalidDateRange as error:
        raise HTTPException(
            status_code=422, detail="`from` must not be after `to`."
        ) from error


@router.get(
    "/coupons/{coupon_id}",
    description="Returns one coupon. Only its owner or an admin can read it.",
    responses={404: {"description": "Coupon not found."}},
)
async def get_coupon(
    database: Annotated[Database, Depends(get_database)],
    x_user_id: Annotated[uuid.UUID, Header()],
    coupon_id: uuid.UUID,
    x_user_role: Annotated[str | None, Header()] = None,
) -> CouponResponse:
    try:
        return await get_coupon_handler(
            database,
            caller_id=x_user_id,
            caller_role=x_user_role,
            coupon_id=coupon_id,
        )
    except CouponNotFound as error:
        raise HTTPException(status_code=404, detail="Coupon not found.") from error


@router.post(
    "/coupons",
    status_code=201,
    description="Buys a coupon for a game. The price is charged from the wallet.",
    responses={
        404: {"description": "Game not found."},
        409: {"description": "Not enough points."},
        502: {"description": "Lotto or wallet failed."},
    },
)
async def create_coupon(
    database: Annotated[Database, Depends(get_database)],
    lotto: Annotated[LottoClient, Depends(get_lotto)],
    wallet: Annotated[WalletClient, Depends(get_wallet)],
    x_user_id: Annotated[uuid.UUID, Header()],
    request: CreateCouponRequest,
) -> CouponResponse:
    try:
        return await create_coupon_handler(
            database,
            lotto,
            wallet,
            user_id=x_user_id,
            game_id=request.game_id,
            numbers=None if request.is_quick_pick else request.numbers,
        )
    except GameNotFound as error:
        raise HTTPException(status_code=404, detail="Game not found.") from error
    except InsufficientFunds as error:
        raise HTTPException(status_code=409, detail="Not enough points.") from error
    except GameNotOpen as error:
        raise HTTPException(
            status_code=422, detail="The game is not open for betting."
        ) from error
    except InvalidNumbers as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except UpstreamError as error:
        raise HTTPException(
            status_code=502, detail=f"The {error} service failed."
        ) from error


@router.get(
    "/games/{game_id}/coupons",
    description=(
        "Lists the coupons of one game, winners first. Numbers are hidden until"
        " the game is drawn."
    ),
)
async def list_game_coupons(
    database: Annotated[Database, Depends(get_database)],
    game_id: uuid.UUID,
    status: CouponStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GameCouponsPageResponse:
    return await list_game_coupons_handler(
        database, game_id=game_id, status=status, limit=limit, offset=offset
    )


def parse_user_ids(
    user_ids: Annotated[str, Query(description="Comma-separated user IDs.")],
) -> list[uuid.UUID]:
    parts = user_ids.split(",")
    if len(parts) > MAX_USER_IDS:
        raise HTTPException(
            status_code=422, detail=f"At most {MAX_USER_IDS} `user_ids` allowed."
        )
    try:
        return [uuid.UUID(part.strip()) for part in parts]
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="`user_ids` must be comma-separated UUIDs."
        ) from error


@router.get(
    "/statistics/coupon-counts",
    description=(
        "Returns how many coupons each user bought. Refunded coupons do not count."
    ),
)
async def count_coupons(
    database: Annotated[Database, Depends(get_database)],
    user_ids: Annotated[list[uuid.UUID], Depends(parse_user_ids)],
) -> list[CouponCountResponse]:
    return await count_coupons_handler(database, user_ids=user_ids)
