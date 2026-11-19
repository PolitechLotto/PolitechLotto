import os
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import (
    AdminAction,
    AdminActionType,
    Report,
    ReportRow,
    ReportType,
    TargetType,
)

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

    async def create_report(
        self,
        admin_id: uuid.UUID,
        report_type: ReportType,
        period_from: date,
        period_to: date,
        rows: Sequence[ReportRow],
    ) -> Report:
        """Saves the report, its rows and the `report_generated` action in one transaction."""
        now = datetime.now(UTC)
        report = Report(
            id=uuid.uuid4(),
            created_by=admin_id,
            type=report_type,
            period_from=period_from,
            period_to=period_to,
            created_at=now,
        )
        for row in rows:
            row.report_id = report.id
        action = AdminAction(
            id=uuid.uuid4(),
            admin_id=admin_id,
            action=AdminActionType.REPORT_GENERATED,
            target_type=TargetType.REPORT,
            target_id=report.id,
            description=(
                f"Generated {report_type} report for {period_from} - {period_to}."
            ),
            created_at=now,
        )

        async with self._session_factory() as session, session.begin():
            session.add(report)
            await session.flush()
            session.add_all([*rows, action])
        return report


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
