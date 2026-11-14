from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from lotto.connectors import get_broker, get_database
from lotto.connectors.broker import MessageBroker
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import (
    GameCreate,
    GameDetails,
    GameOut,
    GamesPage,
    GameTypeNotFoundError,
    InvalidGameError,
    create_game_handler,
    get_game_handler,
    list_games_handler,
)

router = APIRouter(prefix="/v1")

ADMIN_ROLE = "admin"


def require_admin(
    x_user_role: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[UUID | None, Header()] = None,
) -> UUID | None:
    if x_user_role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return x_user_id


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


@router.post(
    "/games",
    status_code=status.HTTP_201_CREATED,
    description="Creates a one-time game.",
    responses={
        403: {"description": "The caller is not an admin"},
        404: {"description": "Game type not found"},
    },
)
async def create_game(
    data: GameCreate,
    admin_id: Annotated[UUID | None, Depends(require_admin)],
    database: Annotated[Database, Depends(get_database)],
    broker: Annotated[MessageBroker, Depends(get_broker)],
) -> GameOut:
    try:
        return await create_game_handler(database, broker, data, admin_id)
    except GameTypeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except InvalidGameError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        ) from e
