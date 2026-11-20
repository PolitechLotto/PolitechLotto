from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class GameCreate(BaseModel):
    game_type_id: UUID
    scheduled_at: AwareDatetime
    name: str | None = Field(default=None, min_length=1, max_length=100)
    ticket_price: int | None = Field(default=None, ge=0)
    jackpot: int | None = Field(default=None, ge=0)
