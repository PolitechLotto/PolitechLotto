import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, Integer, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CouponStatus(StrEnum):
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    REFUNDED = "refunded"


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    game_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    game_type_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    is_quick_pick: Mapped[bool] = mapped_column(Boolean)
    price: Mapped[int] = mapped_column(Integer)
    status: Mapped[CouponStatus] = mapped_column(
        Enum(
            CouponStatus,
            name="coupon_status",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    hits: Mapped[int | None] = mapped_column(Integer)
    points_won: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
