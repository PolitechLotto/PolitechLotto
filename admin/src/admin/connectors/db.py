import os
import uuid
from collections.abc import Sequence
from datetime import datetime
from random import randint
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import AdminAction, AdminActionType, TargetType

DEFAULT_DATABASE_URL = "postgresql+asyncpg://admin:admin@localhost:5432/admin"


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

    async def list_admin_actions(
        self,
        action: AdminActionType | None,
        target_type: TargetType | None,
        admin_id: uuid.UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[AdminAction], int]:
        filters = (action, target_type, admin_id, created_from, created_to)
        count_query = _filter_admin_actions(
            select(func.count()).select_from(AdminAction), *filters
        )
        page_query = (
            _filter_admin_actions(select(AdminAction), *filters)
            .order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
            .limit(limit)
            .offset(offset)
        )

        async with self._session_factory() as session:
            total = (await session.execute(count_query)).scalar_one()
            actions = (await session.execute(page_query)).scalars().all()
        return actions, total


def _filter_admin_actions[Q: Select[Any]](
    query: Q,
    action: AdminActionType | None,
    target_type: TargetType | None,
    admin_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> Q:
    if action is not None:
        query = query.where(AdminAction.action == action)
    if target_type is not None:
        query = query.where(AdminAction.target_type == target_type)
    if admin_id is not None:
        query = query.where(AdminAction.admin_id == admin_id)
    if created_from is not None:
        query = query.where(AdminAction.created_at >= created_from)
    if created_to is not None:
        query = query.where(AdminAction.created_at <= created_to)
    return query
