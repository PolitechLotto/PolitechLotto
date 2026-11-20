from datetime import datetime
from uuid import UUID

from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus

from .models import Game, GameDetails, GamesPage


def _hide_unrevealed[T: Game](game: T) -> T:
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
    games = [_hide_unrevealed(Game.model_validate(game)) for game in result.items]
    return GamesPage(games=games, total=result.total, limit=limit, offset=offset)


async def get_game_handler(database: Database, game_id: UUID) -> GameDetails | None:
    game = await database.get_game(game_id)
    if game is None:
        return None
    return _hide_unrevealed(GameDetails.model_validate(game))
