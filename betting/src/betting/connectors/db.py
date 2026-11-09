import os
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, case, func, select
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

    async def list_coupons_for_game(
        self,
        game_id: uuid.UUID,
        status: CouponStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Coupon]:
        query = select(Coupon).where(Coupon.game_id == game_id)
        if status is not None:
            query = query.where(Coupon.status == status)
        winners_first = case((Coupon.status == CouponStatus.WON, 0), else_=1)

        async with self._session_factory() as session:
            result = await session.execute(
                query.order_by(
                    winners_first,
                    Coupon.points_won.desc().nulls_last(),
                    Coupon.created_at.asc(),
                    Coupon.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

    async def count_coupons_by_users(
        self, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Counts games played: refunded coupons are left out."""
        query = (
            select(Coupon.user_id, func.count())
            .where(
                Coupon.user_id.in_(user_ids),
                Coupon.status != CouponStatus.REFUNDED,
            )
            .group_by(Coupon.user_id)
        )

        async with self._session_factory() as session:
            result = await session.execute(query)
            return {user_id: count for user_id, count in result.all()}

    async def get_coupon(self, coupon_id: uuid.UUID) -> Coupon | None:
        async with self._session_factory() as session:
            result = await session.execute(select(Coupon).where(Coupon.id == coupon_id))
            return result.scalar_one_or_none()

    async def create_coupon(
        self,
        id: uuid.UUID,
        user_id: uuid.UUID,
        game_id: uuid.UUID,
        game_type_id: uuid.UUID,
        numbers: list[int],
        is_quick_pick: bool,
        price: int,
    ) -> Coupon:
        coupon = Coupon(
            id=id,
            user_id=user_id,
            game_id=game_id,
            game_type_id=game_type_id,
            numbers=sorted(numbers),
            is_quick_pick=is_quick_pick,
            price=price,
            status=CouponStatus.ACTIVE,
            hits=None,
            points_won=None,
            created_at=datetime.now(UTC),
        )

        async with self._session_factory() as session:
            session.add(coupon)
            await session.commit()
        return coupon


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
