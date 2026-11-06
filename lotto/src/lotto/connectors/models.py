import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ARRAY, DateTime, Enum, Integer, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GameStatus(StrEnum):
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    game_type_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    game_schedule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String)
    ticket_price: Mapped[int] = mapped_column(Integer)
    jackpot: Mapped[int] = mapped_column(Integer)
    status: Mapped[GameStatus] = mapped_column(
        Enum(
            GameStatus,
            name="game_status",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_hash: Mapped[str] = mapped_column(String)
    seed: Mapped[str | None] = mapped_column(String)
    winning_numbers: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
