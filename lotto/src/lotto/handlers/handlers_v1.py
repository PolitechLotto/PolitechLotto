import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from lotto.connectors.db import Database
from lotto.connectors.models import Game, GameStatus


class GameTypeNotFoundError(Exception):
    pass


class GameTypeInactiveError(Exception):
    pass


class ScheduledAtNotInFutureError(Exception):
    pass


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
class CreateGameData:
    game_type_id: uuid.UUID
    scheduled_at: datetime
    name: str | None = None
    ticket_price: int | None = None
    jackpot: int | None = None


@dataclass(frozen=True)
class SeedCommitment:
    seed: str
    seed_hash: str


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


def generate_seed() -> SeedCommitment:
    seed = secrets.token_bytes(32)
    return SeedCommitment(seed=seed.hex(), seed_hash=hashlib.sha256(seed).hexdigest())


async def create_game_handler(
    database: Database,
    data: CreateGameData,
    now: datetime | None = None,
) -> GameView:
    game_type = await database.get_game_type(data.game_type_id)
    if game_type is None:
        raise GameTypeNotFoundError
    if not game_type.is_active:
        raise GameTypeInactiveError
    if data.scheduled_at <= (now or datetime.now(UTC)):
        raise ScheduledAtNotInFutureError

    name = data.name
    if name is None:
        number = await database.count_games(game_type.id) + 1
        name = f"{game_type.name} #{number}"

    commitment = generate_seed()
    game = await database.create_game(
        {
            "game_type_id": game_type.id,
            "game_schedule_id": None,
            "name": name,
            "ticket_price": (
                game_type.ticket_price
                if data.ticket_price is None
                else data.ticket_price
            ),
            "jackpot": (
                game_type.default_jackpot if data.jackpot is None else data.jackpot
            ),
            "status": GameStatus.SCHEDULED,
            "scheduled_at": data.scheduled_at,
            "seed_hash": commitment.seed_hash,
            "seed": commitment.seed,
        }
    )
    return GameView(**_game_view_fields(game))
