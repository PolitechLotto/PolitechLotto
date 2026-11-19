import uuid
from datetime import UTC, datetime
from typing import Any

from admin.connectors.models import AdminAction, AdminActionType, TargetType


def make_admin_action(**overrides: Any) -> AdminAction:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "admin_id": uuid.uuid4(),
        "action": AdminActionType.GAME_CANCELLED,
        "target_type": TargetType.GAME,
        "target_id": uuid.uuid4(),
        "description": "Cancelled game 6 z 49.",
        "created_at": datetime(2026, 11, 1, 18, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return AdminAction(**fields)
