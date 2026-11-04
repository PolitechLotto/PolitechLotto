import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lotto.connectors.db import Database
from lotto.connectors.models import Game, GameStatus


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


@dataclass(frozen=True)
class GameTypeSummaryView:
    id: uuid.UUID
    name: str
    number_pool_size: int
    number_pick_count: int


@dataclass(frozen=True)
class GameDetailsView(GameView):
    game_type: GameTypeSummaryView


def _game_view_fields(game: Game) -> dict[str, Any]:
    """Public fields of a game. `seed` and `winning_numbers` stay hidden until the game is finished."""
    is_finished = game.status == GameStatus.FINISHED
    return {
        "id": game.id,
        "name": game.name,
        "game_type_id": game.game_type_id,
        "ticket_price": game.ticket_price,
        "jackpot": game.jackpot,
        "status": game.status,
        "scheduled_at": game.scheduled_at,
        "started_at": game.started_at,
        "finished_at": game.finished_at,
        "seed_hash": game.seed_hash,
        "seed": game.seed if is_finished else None,
        "winning_numbers": game.winning_numbers if is_finished else None,
    }


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
    items = [GameView(**_game_view_fields(game)) for game in games]
    return GamesPage(items=items, total=total)


async def get_game_handler(
    database: Database, game_id: uuid.UUID
) -> GameDetailsView | None:
    found = await database.get_game(game_id)
    if found is None:
        return None
    game, game_type = found
    return GameDetailsView(
        **_game_view_fields(game),
        game_type=GameTypeSummaryView(
            id=game_type.id,
            name=game_type.name,
            number_pool_size=game_type.number_pool_size,
            number_pick_count=game_type.number_pick_count,
        ),
    )
