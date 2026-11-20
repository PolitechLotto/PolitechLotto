import hashlib
import logging
import secrets
from datetime import UTC, datetime
from uuid import UUID

from lotto.connectors.broker import MessageBroker
from lotto.connectors.db import Database
from lotto.connectors.models import GameStatus, NewGame

from .models import Game, GameCreate, GameDetails, GamesPage

logger = logging.getLogger(__name__)

GAME_CREATED_EVENT = "game.created"


class GameTypeNotFoundError(Exception):
    pass


class InvalidGameError(Exception):
    pass


def _hide_unrevealed[T: Game](game: T) -> T:
    if game.status is GameStatus.FINISHED:
        return game
    return game.model_copy(update={"seed": None, "winning_numbers": None})


def _generate_seed() -> tuple[str, str]:
    seed = secrets.token_hex(32)
    return seed, hashlib.sha256(seed.encode()).hexdigest()


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


async def create_game_handler(
    database: Database,
    broker: MessageBroker,
    data: GameCreate,
    admin_id: UUID | None,
) -> Game:
    game_type = await database.get_game_type(data.game_type_id)
    if game_type is None:
        raise GameTypeNotFoundError(f"Game type {data.game_type_id} not found")
    if not game_type.is_active:
        raise InvalidGameError("Game type is inactive")
    if data.scheduled_at <= datetime.now(UTC):
        raise InvalidGameError("scheduled_at must be in the future")

    name = data.name
    if name is None:
        number = await database.count_games_of_type(game_type.id) + 1
        name = f"{game_type.name} #{number}"

    seed, seed_hash = _generate_seed()
    game = await database.create_game(
        NewGame(
            game_type_id=game_type.id,
            name=name,
            ticket_price=(
                game_type.ticket_price
                if data.ticket_price is None
                else data.ticket_price
            ),
            jackpot=game_type.default_jackpot if data.jackpot is None else data.jackpot,
            scheduled_at=data.scheduled_at,
            seed=seed,
            seed_hash=seed_hash,
        )
    )

    try:
        await broker.publish(
            GAME_CREATED_EVENT,
            {
                "game_id": str(game.id),
                "game_type_id": str(game.game_type_id),
                "name": game.name,
                "ticket_price": game.ticket_price,
                "jackpot": game.jackpot,
                "scheduled_at": game.scheduled_at.isoformat(),
                "seed_hash": game.seed_hash,
                "created_by": str(admin_id) if admin_id is not None else None,
            },
        )
    except Exception:
        logger.exception(
            "Failed to publish %s for game %s", GAME_CREATED_EVENT, game.id
        )

    return _hide_unrevealed(Game.model_validate(game))
