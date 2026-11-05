import os
import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Game, GameStatus, GameType

DEFAULT_DATABASE_URL = "postgresql+asyncpg://lotto:lotto@localhost:5432/lotto"


class NewGame(TypedDict):
    game_type_id: uuid.UUID
    game_schedule_id: uuid.UUID | None
    name: str
    ticket_price: int
    jackpot: int
    status: GameStatus
    scheduled_at: datetime
    seed_hash: str
    seed: str


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

    async def get_game_type(self, game_type_id: uuid.UUID) -> GameType | None:
        query = select(GameType).where(GameType.id == game_type_id)
        async with self._session_factory() as session:
            return (await session.execute(query)).scalar_one_or_none()

    async def count_games(self, game_type_id: uuid.UUID) -> int:
        query = (
            select(func.count())
            .select_from(Game)
            .where(Game.game_type_id == game_type_id)
        )
        async with self._session_factory() as session:
            return (await session.execute(query)).scalar_one()

    async def create_game(self, data: NewGame) -> Game:
        query = insert(Game).values(**data).returning(Game)
        async with self._session_factory() as session:
            game = (await session.execute(query)).scalar_one()
            await session.commit()
        return game
