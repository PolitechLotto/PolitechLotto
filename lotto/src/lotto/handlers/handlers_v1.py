from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    game_type_id: UUID
    ticket_price: int
    jackpot: int
    status: GameStatus
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    seed_hash: str
    seed: str | None
    winning_numbers: list[int] | None


class GamesPage(BaseModel):
    items: list[GameOut]
    total: int
    limit: int
    offset: int


def _hide_unrevealed(game: GameOut) -> GameOut:
    if game.status is GameStatus.FINISHED:
        return game
    return game.model_copy(update={"seed": None, "winning_numbers": None})


async def list_games_handler(
    database: Database,
    status: GameStatus | None,
    game_type_id: UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> GamesPage:
    result = await database.list_games(
        status, game_type_id, date_from, date_to, limit, offset
    )
    items = [_hide_unrevealed(GameOut.model_validate(game)) for game in result.items]
    return GamesPage(items=items, total=result.total, limit=limit, offset=offset)
