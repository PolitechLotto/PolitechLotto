import uuid
from dataclasses import dataclass
from datetime import datetime

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus


@dataclass(frozen=True)
class GameView:
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


@dataclass(frozen=True)
class GamesPage:
    items: list[GameView]
    total: int


async def list_games_handler(
    database: Database,
    status: GameStatus | None,
    game_type_id: uuid.UUID | None,
    scheduled_from: datetime | None,
    scheduled_to: datetime | None,
    limit: int,
    offset: int,
) -> GamesPage:
    games, total = await database.list_games(
        status=status,
        game_type_id=game_type_id,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        limit=limit,
        offset=offset,
    )
    items = []
    for game in games:
        is_finished = game.status == GameStatus.FINISHED
        items.append(
            GameView(
                id=game.id,
                name=game.name,
                game_type_id=game.game_type_id,
                ticket_price=game.ticket_price,
                jackpot=game.jackpot,
                status=game.status,
                scheduled_at=game.scheduled_at,
                started_at=game.started_at,
                finished_at=game.finished_at,
                seed_hash=game.seed_hash,
                seed=game.seed if is_finished else None,
                winning_numbers=game.winning_numbers if is_finished else None,
            )
        )
    return GamesPage(items=items, total=total)


async def example_handler(database: Database) -> int:
    return await database.get_random_int()
