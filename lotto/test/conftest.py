import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from lotto.connectors.models import (
    Game,
    GameListResult,
    GameStatus,
    GameType,
    NewGame,
)

GAME_TYPE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
GAME_TYPE_NAME = "Lotto"
NUMBER_POOL_SIZE = 49
NUMBER_PICK_COUNT = 6
GAME_NAME = "Lotto 6/49"
TICKET_PRICE = 10
JACKPOT = 1000
SCHEDULED_AT = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
SEED_HASH = "hash"
SEED = "secret-seed"
WINNING_NUMBERS = [1, 2, 3, 4, 5, 6]


def make_game(status: GameStatus = GameStatus.SCHEDULED, **overrides: Any) -> Game:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "game_type_id": GAME_TYPE_ID,
        "game_schedule_id": None,
        "name": GAME_NAME,
        "ticket_price": TICKET_PRICE,
        "jackpot": JACKPOT,
        "status": status,
        "scheduled_at": SCHEDULED_AT,
        "started_at": None,
        "finished_at": None,
        "seed_hash": SEED_HASH,
        "seed": SEED,
        "winning_numbers": WINNING_NUMBERS,
    }
    fields.update(overrides)
    return Game(**fields)


def make_game_type(**overrides: Any) -> GameType:
    fields: dict[str, Any] = {
        "id": GAME_TYPE_ID,
        "name": GAME_TYPE_NAME,
        "description": "Pick 6 numbers out of 49",
        "number_pool_size": NUMBER_POOL_SIZE,
        "number_pick_count": NUMBER_PICK_COUNT,
        "ticket_price": TICKET_PRICE,
        "default_jackpot": JACKPOT,
        "is_active": True,
    }
    fields.update(overrides)
    return GameType(**fields)


def make_game_with_type(
    status: GameStatus = GameStatus.SCHEDULED, **overrides: Any
) -> Game:
    game = make_game(status, **overrides)
    game.game_type = make_game_type()
    return game


class FakeDatabase:
    def __init__(
        self, games: list[Game] | None = None, total: int | None = None
    ) -> None:
        self.games = games or []
        self.total = len(self.games) if total is None else total
        self.calls: list[dict[str, Any]] = []
        self.game_types: list[GameType] = []

    async def list_games(
        self,
        status: GameStatus | None,
        game_type_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> GameListResult:
        self.calls.append(
            {
                "status": status,
                "game_type_id": game_type_id,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
                "offset": offset,
            }
        )
        return GameListResult(items=self.games, total=self.total)

    async def get_game(self, game_id: uuid.UUID) -> Game | None:
        self.calls.append({"game_id": game_id})
        return next((game for game in self.games if game.id == game_id), None)

    async def get_game_type(self, game_type_id: uuid.UUID) -> GameType | None:
        return next((gt for gt in self.game_types if gt.id == game_type_id), None)

    async def count_games_of_type(self, game_type_id: uuid.UUID) -> int:
        return sum(1 for game in self.games if game.game_type_id == game_type_id)

    async def create_game(self, data: NewGame) -> Game:
        self.calls.append({"create_game": data})
        game = make_game(
            GameStatus.SCHEDULED,
            game_type_id=data.game_type_id,
            name=data.name,
            ticket_price=data.ticket_price,
            jackpot=data.jackpot,
            scheduled_at=data.scheduled_at,
            seed=data.seed,
            seed_hash=data.seed_hash,
            winning_numbers=None,
        )
        self.games.append(game)
        return game


class FakeBroker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if self.error is not None:
            raise self.error
        self.published.append((routing_key, payload))


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def fake_broker() -> FakeBroker:
    return FakeBroker()
