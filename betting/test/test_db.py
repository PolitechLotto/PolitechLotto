import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from betting.connectors.db import Database
from betting.connectors.models import CouponStatus

from .factories import make_coupon


class FakeSession:
    """Records executed statements and returns a canned page of coupons."""

    def __init__(self, coupons: list[Any]) -> None:
        self.statements: list[Any] = []
        self._coupons = coupons

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        result.scalars.return_value.all.return_value = self._coupons
        return result


def compile_sql(statement: Any) -> str:
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    return " ".join(sql.split())


def make_database(session: FakeSession) -> Database:
    return Database(session_factory=lambda: session)  # type: ignore[arg-type,return-value]


USER_ID = uuid.UUID(int=1)

DEFAULT_ARGS: dict[str, Any] = {
    "user_id": USER_ID,
    "game_type_id": None,
    "status": None,
    "created_from": None,
    "created_to": None,
    "include_active": True,
    "limit": 50,
    "offset": 0,
}


COUPON_COLUMNS = (
    "coupons.id, coupons.user_id, coupons.game_id, coupons.game_type_id, "
    "coupons.numbers, coupons.is_quick_pick, coupons.price, coupons.status, "
    "coupons.hits, coupons.points_won, coupons.created_at"
)

USER_FILTER = "WHERE coupons.user_id = '00000000-0000-0000-0000-000000000001'"

NEWEST_FIRST = "ORDER BY coupons.created_at DESC, coupons.id DESC"


async def test_list_coupons_returns_coupons() -> None:
    coupons = [make_coupon(), make_coupon()]
    session = FakeSession(coupons=coupons)

    result = await make_database(session).list_coupons(**DEFAULT_ARGS)

    assert list(result) == coupons


async def test_list_coupons_without_filters() -> None:
    session = FakeSession(coupons=[])
    expected = [
        (
            f"SELECT {COUPON_COLUMNS} FROM coupons {USER_FILTER}"
            f" {NEWEST_FIRST} LIMIT 50 OFFSET 0"
        )
    ]

    await make_database(session).list_coupons(**DEFAULT_ARGS)

    assert [compile_sql(s) for s in session.statements] == expected


async def test_list_coupons_applies_filters() -> None:
    session = FakeSession(coupons=[])
    where = (
        f"{USER_FILTER}"
        " AND coupons.game_type_id = '00000000-0000-0000-0000-000000000002'"
        " AND coupons.status = 'won'"
        " AND coupons.created_at >= '2026-11-01 00:00:00+00:00'"
        " AND coupons.created_at <= '2026-11-30 00:00:00+00:00'"
    )
    expected = [
        (
            f"SELECT {COUPON_COLUMNS} FROM coupons {where}"
            f" {NEWEST_FIRST} LIMIT 20 OFFSET 40"
        )
    ]

    await make_database(session).list_coupons(
        user_id=USER_ID,
        game_type_id=uuid.UUID(int=2),
        status=CouponStatus.WON,
        created_from=datetime(2026, 11, 1, tzinfo=UTC),
        created_to=datetime(2026, 11, 30, tzinfo=UTC),
        include_active=True,
        limit=20,
        offset=40,
    )

    assert [compile_sql(s) for s in session.statements] == expected


async def test_list_coupons_excludes_active_coupons() -> None:
    session = FakeSession(coupons=[])
    expected = [
        (
            f"SELECT {COUPON_COLUMNS} FROM coupons {USER_FILTER}"
            " AND coupons.status != 'active'"
            f" {NEWEST_FIRST} LIMIT 50 OFFSET 0"
        )
    ]

    await make_database(session).list_coupons(
        **{**DEFAULT_ARGS, "include_active": False}
    )

    assert [compile_sql(s) for s in session.statements] == expected
