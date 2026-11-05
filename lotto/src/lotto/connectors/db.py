import os
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Game, GameStatus, GameType

DEFAULT_DATABASE_URL = "postgresql+asyncpg://lotto:lotto@localhost:5432/lotto"


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

    async def list_games(
        self,
        status: GameStatus | None,
        game_type_id: uuid.UUID | None,
        scheduled_from: datetime | None,
        scheduled_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Game], int]:
        filtered = _filter_games(
            select(Game), status, game_type_id, scheduled_from, scheduled_to
        )
        count_query = _filter_games(
            select(func.count()).select_from(Game),
            status,
            game_type_id,
            scheduled_from,
            scheduled_to,
        )

        if status == GameStatus.SCHEDULED:
            order = (Game.scheduled_at.asc(), Game.id.asc())
        else:
            order = (Game.scheduled_at.desc(), Game.id.desc())
        page_query = filtered.order_by(*order).limit(limit).offset(offset)

        async with self._session_factory() as session:
            total = (await session.execute(count_query)).scalar_one()
            games = (await session.execute(page_query)).scalars().all()
        return games, total

    async def get_game(self, game_id: uuid.UUID) -> tuple[Game, GameType] | None:
        query = (
            select(Game, GameType)
            .join(GameType, Game.game_type_id == GameType.id)
            .where(Game.id == game_id)
        )
        async with self._session_factory() as session:
            row = (await session.execute(query)).one_or_none()
        if row is None:
            return None
        game, game_type = row
        return game, game_type


def _filter_games[Q: Select[Any]](
    query: Q,
    status: GameStatus | None,
    game_type_id: uuid.UUID | None,
    scheduled_from: datetime | None,
    scheduled_to: datetime | None,
) -> Q:
    if status is not None:
        query = query.where(Game.status == status)
    if game_type_id is not None:
        query = query.where(Game.game_type_id == game_type_id)
    if scheduled_from is not None:
        query = query.where(Game.scheduled_at >= scheduled_from)
    if scheduled_to is not None:
        query = query.where(Game.scheduled_at <= scheduled_to)
    return query

