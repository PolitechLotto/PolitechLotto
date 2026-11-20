from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from lotto.connectors.models import GameStatus


class Game(BaseModel):
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
    games: list[Game]
    total: int
    limit: int
    offset: int


class GameTypeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    number_pool_size: int
    number_pick_count: int


class GameDetails(Game):
    game_type: GameTypeSummary
