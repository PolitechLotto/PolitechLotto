import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any, Self
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from admin.connectors.db import Database
from admin.connectors.models import AdminActionType, ReportType, TargetType

from .factories import (
    make_admin_action,
    make_daily_summary_row,
    make_game_stats_row,
    make_user_activity_row,
)


class FakeSession:
    """Records executed statements and returns canned results: the count first, then the page."""

    def __init__(self, total: int, rows: list[Any]) -> None:
        self.statements: list[Any] = []
        self._total = total
        self._rows = rows

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        if len(self.statements) == 1:
            result.scalar_one.return_value = self._total
        else:
            result.scalars.return_value.all.return_value = self._rows
        return result


def compile_sql(statement: Any) -> str:
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    return " ".join(sql.split())


def make_database(session: Any) -> Database:
    return Database(session_factory=lambda: session)  # type: ignore[arg-type,return-value]


ADMIN_ACTION_COLUMNS = (
    "admin_actions.id, admin_actions.admin_id, admin_actions.action,"
    " admin_actions.target_type, admin_actions.target_id,"
    " admin_actions.description, admin_actions.created_at"
)

DEFAULT_ACTIONS_ARGS: dict[str, Any] = {
    "action": None,
    "target_type": None,
    "admin_id": None,
    "created_from": None,
    "created_to": None,
    "limit": 50,
    "offset": 0,
}


async def test_list_admin_actions_returns_actions_and_total() -> None:
    actions = [make_admin_action(), make_admin_action()]
    session = FakeSession(total=7, rows=actions)

    result, total = await make_database(session).list_admin_actions(
        **DEFAULT_ACTIONS_ARGS
    )

    assert (list(result), total) == (actions, 7)


async def test_list_admin_actions_without_filters_sorts_newest_first() -> None:
    session = FakeSession(total=0, rows=[])
    expected = [
        "SELECT count(*) AS count_1 FROM admin_actions",
        (
            f"SELECT {ADMIN_ACTION_COLUMNS} FROM admin_actions"
            " ORDER BY admin_actions.created_at DESC, admin_actions.id DESC"
            " LIMIT 50 OFFSET 0"
        ),
    ]

    await make_database(session).list_admin_actions(**DEFAULT_ACTIONS_ARGS)

    assert [compile_sql(s) for s in session.statements] == expected


async def test_list_admin_actions_applies_filters_to_count_and_page() -> None:
    session = FakeSession(total=0, rows=[])
    where = (
        "WHERE admin_actions.action = 'points_adjusted'"
        " AND admin_actions.target_type = 'wallet'"
        " AND admin_actions.admin_id = '00000000-0000-0000-0000-000000000001'"
        " AND admin_actions.created_at >= '2026-11-01 00:00:00+00:00'"
        " AND admin_actions.created_at <= '2026-11-30 00:00:00+00:00'"
    )
    expected = [
        f"SELECT count(*) AS count_1 FROM admin_actions {where}",
        (
            f"SELECT {ADMIN_ACTION_COLUMNS} FROM admin_actions {where}"
            " ORDER BY admin_actions.created_at DESC, admin_actions.id DESC"
            " LIMIT 20 OFFSET 40"
        ),
    ]

    await make_database(session).list_admin_actions(
        action=AdminActionType.POINTS_ADJUSTED,
        target_type=TargetType.WALLET,
        admin_id=uuid.UUID(int=1),
        created_from=datetime(2026, 11, 1, tzinfo=UTC),
        created_to=datetime(2026, 11, 30, tzinfo=UTC),
        limit=20,
        offset=40,
    )

    assert [compile_sql(s) for s in session.statements] == expected


class FakeWriteSession:
    """Records what is added and flushed, and whether the transaction was committed."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield
        self.events.append(("commit", None))

    def add(self, instance: Any) -> None:
        self.events.append(("add", instance))

    def add_all(self, instances: list[Any]) -> None:
        self.events.extend(("add", instance) for instance in instances)

    async def flush(self) -> None:
        self.events.append(("flush", None))


async def test_create_report_saves_report_rows_and_action_in_one_transaction() -> None:
    session = FakeWriteSession()
    admin_id = uuid.UUID(int=1)
    rows = [make_daily_summary_row(), make_daily_summary_row(day=date(2026, 11, 2))]

    report = await make_database(session).create_report(
        admin_id,
        ReportType.DAILY_SUMMARY,
        date(2026, 11, 1),
        date(2026, 11, 2),
        rows,
    )

    action = session.events[4][1]
    assert session.events == [
        ("add", report),
        ("flush", None),
        ("add", rows[0]),
        ("add", rows[1]),
        ("add", action),
        ("commit", None),
    ]
    assert (
        report.created_by,
        report.type,
        report.period_from,
        report.period_to,
        report.created_at.tzinfo,
    ) == (admin_id, ReportType.DAILY_SUMMARY, date(2026, 11, 1), date(2026, 11, 2), UTC)
    assert [row.report_id for row in rows] == [report.id, report.id]
    assert (
        action.admin_id,
        action.action,
        action.target_type,
        action.target_id,
        action.description,
        action.created_at,
    ) == (
        admin_id,
        AdminActionType.REPORT_GENERATED,
        TargetType.REPORT,
        report.id,
        "Generated daily_summary report for 2026-11-01 - 2026-11-02.",
        report.created_at,
    )


@pytest.mark.parametrize(
    ("report_type", "make_row"),
    [
        (ReportType.GAME_STATS, make_game_stats_row),
        (ReportType.USER_ACTIVITY, make_user_activity_row),
    ],
)
async def test_create_report_saves_rows_of_any_type(
    report_type: ReportType, make_row: Any
) -> None:
    session = FakeWriteSession()
    row = make_row()

    report = await make_database(session).create_report(
        uuid.uuid4(), report_type, date(2026, 11, 1), date(2026, 11, 30), [row]
    )

    assert (session.events[2], row.report_id) == (("add", row), report.id)
