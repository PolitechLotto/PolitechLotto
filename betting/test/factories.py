import uuid
from datetime import UTC, datetime
from typing import Any

from betting.connectors.models import Coupon, CouponStatus


def make_coupon(**overrides: Any) -> Coupon:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "game_id": uuid.uuid4(),
        "game_type_id": uuid.uuid4(),
        "numbers": [1, 2, 3, 4, 5, 6],
        "is_quick_pick": False,
        "price": 10,
        "status": CouponStatus.WON,
        "hits": 3,
        "points_won": 20,
        "created_at": datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return Coupon(**fields)
