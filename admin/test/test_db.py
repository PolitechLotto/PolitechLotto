import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from admin.connectors.db import Database
from admin.connectors.models import AdminActionType, TargetType

from .factories import make_admin_action


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
