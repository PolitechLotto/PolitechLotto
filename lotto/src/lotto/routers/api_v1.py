import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict

from lotto.connectors import get_database
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import list_games_handler

router = APIRouter(prefix="/v1")


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    game_type_id: uuid.UUID
    ticket_price: int
    jackpot: int
    status: GameStatus
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    seed_hash: str
    seed: str | None
    winning_numbers: list[int] | None


class GamesPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[GameResponse]
    total: int


@router.get("/games", description="Lists games (draws).")
async def list_games(
    database: Annotated[Database, Depends(get_database)],
    status: GameStatus | None = None,
    game_type_id: uuid.UUID | None = None,
    scheduled_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    scheduled_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GamesPageResponse:
    page = await list_games_handler(
        database,
        status=status,
        game_type_id=game_type_id,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        limit=limit,
        offset=offset,
    )
    return GamesPageResponse.model_validate(page)
