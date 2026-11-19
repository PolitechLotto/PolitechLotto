import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _enum_values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class AdminActionType(StrEnum):
    USER_DELETED = "user_deleted"
    POINTS_ADJUSTED = "points_adjusted"
    GAME_TYPE_CREATED = "game_type_created"
    GAME_TYPE_UPDATED = "game_type_updated"
    GAME_TYPE_DISABLED = "game_type_disabled"
    GAME_SCHEDULE_CREATED = "game_schedule_created"
    GAME_SCHEDULE_UPDATED = "game_schedule_updated"
    GAME_SCHEDULE_DISABLED = "game_schedule_disabled"
    GAME_CREATED = "game_created"
    GAME_CANCELLED = "game_cancelled"
    REPORT_GENERATED = "report_generated"


class TargetType(StrEnum):
    USER = "user"
    WALLET = "wallet"
    GAME_TYPE = "game_type"
    GAME_SCHEDULE = "game_schedule"
    GAME = "game"
    REPORT = "report"


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[AdminActionType] = mapped_column(
        Enum(AdminActionType, name="admin_action_type", values_callable=_enum_values)
    )
    target_type: Mapped[TargetType] = mapped_column(
        Enum(TargetType, name="target_type", values_callable=_enum_values)
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    description: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportType(StrEnum):
    DAILY_SUMMARY = "daily_summary"
    GAME_STATS = "game_stats"
    USER_ACTIVITY = "user_activity"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="report_type", values_callable=_enum_values)
    )
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailySummaryReportRow(Base):
    __tablename__ = "daily_summary_report_rows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("reports.id"))
    day: Mapped[date] = mapped_column(Date)
    games_played: Mapped[int] = mapped_column(Integer)
    active_players: Mapped[int] = mapped_column(Integer)
    points_spent: Mapped[int] = mapped_column(Integer)
    points_awarded: Mapped[int] = mapped_column(Integer)


class GameStatsReportRow(Base):
    __tablename__ = "game_stats_report_rows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("reports.id"))
    game_type_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    games_played: Mapped[int] = mapped_column(Integer)
    coupons_sold: Mapped[int] = mapped_column(Integer)
    points_spent: Mapped[int] = mapped_column(Integer)
    points_awarded: Mapped[int] = mapped_column(Integer)


class UserActivityReportRow(Base):
    __tablename__ = "user_activity_report_rows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("reports.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    coupons_bought: Mapped[int] = mapped_column(Integer)
    points_spent: Mapped[int] = mapped_column(Integer)
    points_won: Mapped[int] = mapped_column(Integer)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


ReportRow = DailySummaryReportRow | GameStatsReportRow | UserActivityReportRow
