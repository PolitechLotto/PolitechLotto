import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from .models import Game, GameStatus, GameType


@dataclass(frozen=True)
class GameListResult:
    items: list[Game]
    total: int


@dataclass(frozen=True)
class NewGame:
    game_type_id: uuid.UUID
    name: str
    ticket_price: int
    jackpot: int
    scheduled_at: datetime
    seed: str
    seed_hash: str


def _games_filters(
    status: GameStatus | None,
    game_type_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if status is not None:
        filters.append(Game.status == status)
    if game_type_id is not None:
        filters.append(Game.game_type_id == game_type_id)
    if date_from is not None:
        filters.append(Game.scheduled_at >= date_from)
    if date_to is not None:
        filters.append(Game.scheduled_at <= date_to)
    return filters


def build_list_games_query(
    status: GameStatus | None,
    game_type_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> Select[Game]:
    filters = _games_filters(status, game_type_id, date_from, date_to)
    if status is GameStatus.SCHEDULED:
        order = (Game.scheduled_at.asc(), Game.id.asc())
    else:
        order = (Game.scheduled_at.desc(), Game.id.desc())
    return select(Game).where(*filters).order_by(*order).limit(limit).offset(offset)


def build_count_games_query(
    status: GameStatus | None,
    game_type_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select[int]:
    filters = _games_filters(status, game_type_id, date_from, date_to)
    return select(func.count()).select_from(Game).where(*filters)


def build_get_game_query(game_id: uuid.UUID) -> Select[Game]:
    return (
        select(Game)
        .options(joinedload(Game.game_type, innerjoin=True))
        .where(Game.id == game_id)
    )


class Database:
    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_games(
        self,
        status: GameStatus | None,
        game_type_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> GameListResult:
        items_query = build_list_games_query(
            status, game_type_id, date_from, date_to, limit, offset
        )
        count_query = build_count_games_query(status, game_type_id, date_from, date_to)
        async with self._sessionmaker() as session:
            items = list((await session.scalars(items_query)).all())
            total = await session.scalar(count_query) or 0
        return GameListResult(items=items, total=total)

    async def get_game(self, game_id: uuid.UUID) -> Game | None:
        async with self._sessionmaker() as session:
            return await session.scalar(build_get_game_query(game_id))

    async def get_game_type(self, game_type_id: uuid.UUID) -> GameType | None:
        async with self._sessionmaker() as session:
            return await session.get(GameType, game_type_id)

    async def count_games_of_type(self, game_type_id: uuid.UUID) -> int:
        query = build_count_games_query(None, game_type_id, None, None)
        async with self._sessionmaker() as session:
            return await session.scalar(query) or 0

    async def create_game(self, data: NewGame) -> Game:
        game = Game(
            game_type_id=data.game_type_id,
            game_schedule_id=None,
            name=data.name,
            ticket_price=data.ticket_price,
            jackpot=data.jackpot,
            status=GameStatus.SCHEDULED,
            scheduled_at=data.scheduled_at,
            seed_hash=data.seed_hash,
            seed=data.seed,
        )
        async with self._sessionmaker() as session:
            session.add(game)
            await session.commit()
        return game
