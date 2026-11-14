import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from lotto.connectors.db import GameListResult
from lotto.connectors.models import Game, GameStatus

GAME_TYPE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def make_game(status: GameStatus = GameStatus.SCHEDULED, **overrides: Any) -> Game:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "game_type_id": GAME_TYPE_ID,
        "game_schedule_id": None,
        "name": "Lotto 6/49",
        "ticket_price": 10,
        "jackpot": 1000,
        "status": status,
        "scheduled_at": datetime(2026, 11, 20, 18, 0, tzinfo=UTC),
        "started_at": None,
        "finished_at": None,
        "seed_hash": "hash",
        "seed": "secret-seed",
        "winning_numbers": [1, 2, 3, 4, 5, 6],
    }
    fields.update(overrides)
    return Game(**fields)


class FakeDatabase:
    def __init__(
        self, games: list[Game] | None = None, total: int | None = None
    ) -> None:
        self.games = games or []
        self.total = len(self.games) if total is None else total
        self.calls: list[dict[str, Any]] = []

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


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()
