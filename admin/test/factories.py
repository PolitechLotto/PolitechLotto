import uuid
from datetime import UTC, date, datetime
from typing import Any

from admin.connectors.models import (
    AdminAction,
    AdminActionType,
    DailySummaryReportRow,
    GameStatsReportRow,
    TargetType,
    UserActivityReportRow,
)


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


def make_daily_summary_row(**overrides: Any) -> DailySummaryReportRow:
    fields: dict[str, Any] = {
        "day": date(2026, 11, 1),
        "games_played": 4,
        "active_players": 12,
        "points_spent": 480,
        "points_awarded": 150,
    }
    fields.update(overrides)
    return DailySummaryReportRow(**fields)


def make_game_stats_row(**overrides: Any) -> GameStatsReportRow:
    fields: dict[str, Any] = {
        "game_type_id": uuid.uuid4(),
        "games_played": 4,
        "coupons_sold": 48,
        "points_spent": 480,
        "points_awarded": 150,
    }
    fields.update(overrides)
    return GameStatsReportRow(**fields)


def make_user_activity_row(**overrides: Any) -> UserActivityReportRow:
    fields: dict[str, Any] = {
        "user_id": uuid.uuid4(),
        "coupons_bought": 5,
        "points_spent": 50,
        "points_won": 20,
        "last_seen_at": datetime(2026, 11, 2, 9, 30, tzinfo=UTC),
    }
    fields.update(overrides)
    return UserActivityReportRow(**fields)
