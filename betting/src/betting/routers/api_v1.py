import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import AwareDatetime

from betting.connectors import get_database
from betting.connectors.db import Database
from betting.connectors.models import CouponStatus
from betting.exceptions import InvalidDateRange
from betting.handlers.handlers_v1 import CouponsPageResponse, list_coupons_handler

router = APIRouter(prefix="/v1")


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
