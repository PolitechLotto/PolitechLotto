import os
import uuid
from collections.abc import Sequence
from datetime import datetime
from random import randint
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Coupon, CouponStatus

DEFAULT_DATABASE_URL = "postgresql+asyncpg://betting:betting@localhost:5432/betting"


def create_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    return async_sessionmaker(engine, expire_on_commit=False)


class Database:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        self._session_factory = session_factory or create_session_factory()

    async def get_random_int(self) -> int:
        return randint(0, 10)

    async def list_coupons(
        self,
        user_id: uuid.UUID,
        game_type_id: uuid.UUID | None,
        status: CouponStatus | None,
        created_from: datetime | None,
        created_to: datetime | None,
        include_active: bool,
        limit: int,
        offset: int,
    ) -> Sequence[Coupon]:
        query = _filter_coupons(
            select(Coupon).where(Coupon.user_id == user_id),
            game_type_id,
            status,
            created_from,
            created_to,
            include_active,
        )

        async with self._session_factory() as session:
            result = await session.execute(
                query.order_by(Coupon.created_at.desc(), Coupon.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()


def _filter_coupons[Q: Select[Any]](
    query: Q,
    game_type_id: uuid.UUID | None,
    status: CouponStatus | None,
    created_from: datetime | None,
    created_to: datetime | None,
    include_active: bool,
) -> Q:
    if game_type_id is not None:
        query = query.where(Coupon.game_type_id == game_type_id)
    if status is not None:
        query = query.where(Coupon.status == status)
    if not include_active:
        query = query.where(Coupon.status != CouponStatus.ACTIVE)
    if created_from is not None:
        query = query.where(Coupon.created_at >= created_from)
    if created_to is not None:
        query = query.where(Coupon.created_at <= created_to)
    return query
