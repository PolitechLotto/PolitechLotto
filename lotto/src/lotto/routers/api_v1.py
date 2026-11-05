import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from lotto.connectors import get_database
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus
from lotto.handlers.handlers_v1 import (
    CreateGameData,
    GameTypeInactiveError,
    GameTypeNotFoundError,
    ScheduledAtNotInFutureError,
    create_game_handler,
)

router = APIRouter(prefix="/v1")

ADMIN_ROLE = "admin"


def require_admin(
    x_user_role: Annotated[str | None, Header()] = None,
) -> None:
    """The gateway (ADR 004) verifies the JWT and passes the user's role in `X-User-Role`."""
    if x_user_role != ADMIN_ROLE:
        raise HTTPException(HTTPStatus.FORBIDDEN, detail="Admin role required.")


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


class CreateGameRequest(BaseModel):
    game_type_id: uuid.UUID
    scheduled_at: AwareDatetime
    name: Annotated[str | None, Field(min_length=1)] = None
    ticket_price: Annotated[int | None, Field(ge=0)] = None
    jackpot: Annotated[int | None, Field(ge=0)] = None


@router.post(
    "/games",
    status_code=HTTPStatus.CREATED,
    description="Creates a one-time game (draw).",
    dependencies=[Depends(require_admin)],
    responses={
        HTTPStatus.FORBIDDEN: {"description": "The caller is not an admin."},
        HTTPStatus.NOT_FOUND: {"description": "Game type not found."},
    },
)
async def create_game(
    database: Annotated[Database, Depends(get_database)],
    body: CreateGameRequest,
) -> GameResponse:
    try:
        game = await create_game_handler(database, CreateGameData(**body.model_dump()))
    except GameTypeNotFoundError:
        raise HTTPException(
            HTTPStatus.NOT_FOUND, detail="Game type not found."
        ) from None
    except GameTypeInactiveError:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY, detail="Game type is inactive."
        ) from None
    except ScheduledAtNotInFutureError:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="scheduled_at must be in the future.",
        ) from None
    return GameResponse.model_validate(game)
