from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from lotto.connectors import get_database
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import (
    GameDetails,
    GamesPage,
    get_game_handler,
    list_games_handler,
)

router = APIRouter(prefix="/v1")


@router.get("/games", description="Lists games (draws) for the dashboard.")
async def list_games(
    database: Annotated[Database, Depends(get_database)],
    status: GameStatus | None = None,
    game_type_id: UUID | None = None,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GamesPage:
    return await list_games_handler(
        database, status, game_type_id, date_from, date_to, limit, offset
    )


@router.get(
    "/games/{game_id}",
    description="Returns one game for the game details page.",
    responses={404: {"description": "Game not found"}},
)
async def get_game(
    database: Annotated[Database, Depends(get_database)],
    game_id: UUID,
) -> GameDetails:
    game = await get_game_handler(database, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game
