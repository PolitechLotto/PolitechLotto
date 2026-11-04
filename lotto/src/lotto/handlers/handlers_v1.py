import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from lotto.connectors.db import Database
from lotto.connectors.models import Game, GameStatus, SortOrder
from lotto.exceptions import InvalidDateRange


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
    items: list[GameResponse]


def _to_response(game: Game) -> GameResponse:
    response = GameResponse.model_validate(game)
    if game.status == GameStatus.FINISHED:
        return response
    return response.model_copy(update={"seed": None, "winning_numbers": None})


async def list_games_handler(
    database: Database,
    status: GameStatus | None,
    game_type_id: uuid.UUID | None,
    scheduled_from: datetime | None,
    scheduled_to: datetime | None,
    order: SortOrder | None,
    limit: int,
    offset: int,
) -> GamesPageResponse:
    if scheduled_from and scheduled_to and scheduled_from > scheduled_to:
        raise InvalidDateRange
    if order is None:
        order = SortOrder.ASC if status == GameStatus.SCHEDULED else SortOrder.DESC
    games = await database.list_games(
        status=status,
        game_type_id=game_type_id,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        order=order,
        limit=limit,
        offset=offset,
    )
    return GamesPageResponse(items=[_to_response(game) for game in games])


async def example_handler(database: Database) -> int:
    return await database.get_random_int()
