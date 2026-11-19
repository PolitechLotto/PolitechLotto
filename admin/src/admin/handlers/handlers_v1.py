import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from admin.connectors.db import Database
from admin.connectors.models import (
    AdminAction,
    AdminActionType,
    DailySummaryReportRow,
    GameStatsReportRow,
    Report,
    ReportRow,
    ReportType,
    TargetType,
    UserActivityReportRow,
)
from admin.connectors.services import AuthClient, BettingClient, LottoClient

MAX_REPORT_DAYS = 366


@dataclass(frozen=True)
class AdminActionView:
    id: uuid.UUID
    admin_id: uuid.UUID
    action: AdminActionType
    target_type: TargetType
    target_id: uuid.UUID
    description: str
    created_at: datetime


@dataclass(frozen=True)
class AdminActionsPage:
    items: list[AdminActionView]
    total: int


def _admin_action_view(action: AdminAction) -> AdminActionView:
    return AdminActionView(
        id=action.id,
        admin_id=action.admin_id,
        action=action.action,
        target_type=action.target_type,
        target_id=action.target_id,
        description=action.description,
        created_at=action.created_at,
    )


async def list_admin_actions_handler(
    database: Database,
    action: AdminActionType | None,
    target_type: TargetType | None,
    admin_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    offset: int,
) -> AdminActionsPage:
    actions, total = await database.list_admin_actions(
        action=action,
        target_type=target_type,
        admin_id=admin_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return AdminActionsPage(
        items=[_admin_action_view(admin_action) for admin_action in actions],
        total=total,
    )


class InvalidReportPeriodError(ValueError):
    pass


@dataclass(frozen=True)
class DailySummaryRowView:
    day: date
    games_played: int
    active_players: int
    points_spent: int
    points_awarded: int


@dataclass(frozen=True)
class GameStatsRowView:
    game_type_id: uuid.UUID
    games_played: int
    coupons_sold: int
    points_spent: int
    points_awarded: int


@dataclass(frozen=True)
class UserActivityRowView:
    user_id: uuid.UUID
    coupons_bought: int
    points_spent: int
    points_won: int
    last_seen_at: datetime | None


ReportRowView = DailySummaryRowView | GameStatsRowView | UserActivityRowView


@dataclass(frozen=True)
class ReportView:
    id: uuid.UUID
    type: ReportType
    period_from: date
    period_to: date
    created_by: uuid.UUID
    created_at: datetime


@dataclass(frozen=True)
class ReportDetailsView(ReportView):
    rows: list[ReportRowView]


def _report_view_fields(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "type": report.type,
        "period_from": report.period_from,
        "period_to": report.period_to,
        "created_by": report.created_by,
        "created_at": report.created_at,
    }


def _row_view(row: ReportRow) -> ReportRowView:
    match row:
        case DailySummaryReportRow():
            return DailySummaryRowView(
                day=row.day,
                games_played=row.games_played,
                active_players=row.active_players,
                points_spent=row.points_spent,
                points_awarded=row.points_awarded,
            )
        case GameStatsReportRow():
            return GameStatsRowView(
                game_type_id=row.game_type_id,
                games_played=row.games_played,
                coupons_sold=row.coupons_sold,
                points_spent=row.points_spent,
                points_awarded=row.points_awarded,
            )
        case UserActivityReportRow():
            return UserActivityRowView(
                user_id=row.user_id,
                coupons_bought=row.coupons_bought,
                points_spent=row.points_spent,
                points_won=row.points_won,
                last_seen_at=row.last_seen_at,
            )


def _report_details_view(
    report: Report, rows: Sequence[ReportRow]
) -> ReportDetailsView:
    return ReportDetailsView(
        **_report_view_fields(report), rows=[_row_view(row) for row in rows]
    )


def _check_report_period(period_from: date, period_to: date) -> None:
    if period_from > period_to:
        raise InvalidReportPeriodError("period_from is after period_to.")
    if (period_to - period_from).days + 1 > MAX_REPORT_DAYS:
        raise InvalidReportPeriodError(
            f"The period is longer than {MAX_REPORT_DAYS} days."
        )


async def _daily_summary_rows(
    lotto: LottoClient, betting: BettingClient, period_from: date, period_to: date
) -> list[DailySummaryReportRow]:
    games, coupons = await asyncio.gather(
        lotto.games_by_day(period_from, period_to),
        betting.coupon_stats_by_day(period_from, period_to),
    )
    games_by_day = {row.day: row.games_played for row in games}
    coupons_by_day = {row.day: row for row in coupons}
    rows = []
    for day in sorted(games_by_day.keys() | coupons_by_day.keys()):
        stats = coupons_by_day.get(day)
        rows.append(
            DailySummaryReportRow(
                day=day,
                games_played=games_by_day.get(day, 0),
                active_players=stats.active_players if stats else 0,
                points_spent=stats.points_spent if stats else 0,
                points_awarded=stats.points_awarded if stats else 0,
            )
        )
    return rows


async def _game_stats_rows(
    lotto: LottoClient, betting: BettingClient, period_from: date, period_to: date
) -> list[GameStatsReportRow]:
    """One row per game type, most coupons sold first."""
    games, coupons = await asyncio.gather(
        lotto.games_by_game_type(period_from, period_to),
        betting.coupon_stats_by_game_type(period_from, period_to),
    )
    games_by_type = {row.game_type_id: row.games_played for row in games}
    coupons_by_type = {row.game_type_id: row for row in coupons}
    rows = []
    for game_type_id in games_by_type.keys() | coupons_by_type.keys():
        stats = coupons_by_type.get(game_type_id)
        rows.append(
            GameStatsReportRow(
                game_type_id=game_type_id,
                games_played=games_by_type.get(game_type_id, 0),
                coupons_sold=stats.coupons_sold if stats else 0,
                points_spent=stats.points_spent if stats else 0,
                points_awarded=stats.points_awarded if stats else 0,
            )
        )
    rows.sort(key=lambda row: (-row.coupons_sold, str(row.game_type_id)))
    return rows


async def _user_activity_rows(
    betting: BettingClient, auth: AuthClient, period_from: date, period_to: date
) -> list[UserActivityReportRow]:
    """One row per player who bought a coupon in the period, most coupons first."""
    coupons = await betting.coupon_stats_by_user(period_from, period_to)
    users = await auth.get_users([row.user_id for row in coupons])
    last_seen = {user.id: user.last_seen_at for user in users}
    rows = [
        UserActivityReportRow(
            user_id=row.user_id,
            coupons_bought=row.coupons_sold,
            points_spent=row.points_spent,
            points_won=row.points_awarded,
            last_seen_at=last_seen.get(row.user_id),
        )
        for row in coupons
    ]
    rows.sort(key=lambda row: (-row.coupons_bought, str(row.user_id)))
    return rows


async def create_report_handler(
    database: Database,
    lotto: LottoClient,
    betting: BettingClient,
    auth: AuthClient,
    admin_id: uuid.UUID,
    report_type: ReportType,
    period_from: date,
    period_to: date,
) -> ReportDetailsView:
    """Collects statistics from the other services and saves them as a report.

    Raises `InvalidReportPeriodError` for a bad period and `ServiceError` when a service fails.
    """
    _check_report_period(period_from, period_to)
    rows: Sequence[ReportRow]
    match report_type:
        case ReportType.DAILY_SUMMARY:
            rows = await _daily_summary_rows(lotto, betting, period_from, period_to)
        case ReportType.GAME_STATS:
            rows = await _game_stats_rows(lotto, betting, period_from, period_to)
        case ReportType.USER_ACTIVITY:
            rows = await _user_activity_rows(betting, auth, period_from, period_to)
    report = await database.create_report(
        admin_id, report_type, period_from, period_to, rows
    )
    return _report_details_view(report, rows)
