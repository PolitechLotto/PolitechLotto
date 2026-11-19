import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Uuid
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
