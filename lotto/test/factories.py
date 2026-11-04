import uuid
from datetime import UTC, datetime
from typing import Any

from lotto.connectors.models import Game, GameStatus


def make_game(**overrides: Any) -> Game:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "game_type_id": uuid.uuid4(),
        "game_schedule_id": None,
        "name": "6 z 49",
        "ticket_price": 10,
        "jackpot": 1000,
        "status": GameStatus.FINISHED,
        "scheduled_at": datetime(2026, 11, 1, 18, 0, tzinfo=UTC),
        "started_at": datetime(2026, 11, 1, 18, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 11, 1, 18, 5, tzinfo=UTC),
        "seed_hash": "hash",
        "seed": "seed",
        "winning_numbers": [1, 2, 3, 4, 5, 6],
    }
    fields.update(overrides)
    return Game(**fields)
