import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime

from lotto.connectors import get_database
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus, SortOrder
from lotto.exceptions import InvalidDateRange
from lotto.handlers.handlers_v1 import GamesPageResponse, list_games_handler

router = APIRouter(prefix="/v1")


@router.get("/games", description="Lists games (draws).")
async def list_games(
    database: Annotated[Database, Depends(get_database)],
    status: GameStatus | None = None,
    game_type_id: uuid.UUID | None = None,
    scheduled_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    scheduled_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    order: SortOrder | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GamesPageResponse:
    try:
        return await list_games_handler(
            database,
            status=status,
            game_type_id=game_type_id,
            scheduled_from=scheduled_from,
            scheduled_to=scheduled_to,
            order=order,
            limit=limit,
            offset=offset,
        )
    except InvalidDateRange as error:
        raise HTTPException(
            status_code=422, detail="`from` must not be after `to`."
        ) from error
