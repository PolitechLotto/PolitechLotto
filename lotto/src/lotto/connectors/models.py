import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GameStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class GameType(Base):
    __tablename__ = "game_types"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    number_pool_size: Mapped[int] = mapped_column(Integer)
    number_pick_count: Mapped[int] = mapped_column(Integer)
    ticket_price: Mapped[int] = mapped_column(Integer)
    default_jackpot: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)


class PrizeTier(Base):
    __tablename__ = "prize_tiers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_types.id"))
    hits: Mapped[int] = mapped_column(Integer)
    fixed_prize: Mapped[int] = mapped_column(Integer)


class GameSchedule(Base):
    __tablename__ = "game_schedules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_types.id"))
    interval_minutes: Mapped[int] = mapped_column(Integer)
    next_game_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_types.id"), index=True
    )
    game_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("game_schedules.id")
    )
    name: Mapped[str] = mapped_column(String)
    ticket_price: Mapped[int] = mapped_column(Integer)
    jackpot: Mapped[int] = mapped_column(Integer)
    status: Mapped[GameStatus] = mapped_column(
        Enum(
            GameStatus,
            name="game_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=GameStatus.SCHEDULED,
        index=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_hash: Mapped[str] = mapped_column(String)
    seed: Mapped[str] = mapped_column(String)
    winning_numbers: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
