import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from betting.connectors import db
from betting.connectors.db import Database
from betting.connectors.models import Coupon, CouponStatus

from .factories import make_coupon


class FakeSession:
    """Records executed statements and returns a canned page of coupons."""

    def __init__(self, coupons: list[Any]) -> None:
        self.statements: list[Any] = []
        self.added: list[Any] = []
        self.commits = 0
        self._coupons = coupons

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: Any) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        result.scalars.return_value.all.return_value = self._coupons
        result.scalar_one_or_none.return_value = (
            self._coupons[0] if self._coupons else None
        )
        return result

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commits += 1


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


NOW = datetime(2026, 11, 9, 18, 0, tzinfo=UTC)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> Self:
        return cls.fromtimestamp(NOW.timestamp(), tz)


def coupon_columns(coupon: Coupon) -> dict[str, Any]:
    return {column.key: getattr(coupon, column.key) for column in Coupon.__table__.c}


async def test_create_coupon_saves_active_coupon_with_sorted_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db, "datetime", FrozenDatetime)
    session = FakeSession(coupons=[])
    expected = (
        [
            {
                "id": uuid.UUID(int=10),
                "user_id": USER_ID,
                "game_id": uuid.UUID(int=11),
                "game_type_id": uuid.UUID(int=12),
                "numbers": [3, 7, 19, 22, 41, 48],
                "is_quick_pick": False,
                "price": 10,
                "status": CouponStatus.ACTIVE,
                "hits": None,
                "points_won": None,
                "created_at": NOW,
            }
        ],
        1,
    )

    await make_database(session).create_coupon(
        id=uuid.UUID(int=10),
        user_id=USER_ID,
        game_id=uuid.UUID(int=11),
        game_type_id=uuid.UUID(int=12),
        numbers=[41, 3, 22, 48, 7, 19],
        is_quick_pick=False,
        price=10,
    )

    assert ([coupon_columns(c) for c in session.added], session.commits) == expected


async def test_create_coupon_returns_saved_coupon() -> None:
    session = FakeSession(coupons=[])

    coupon = await make_database(session).create_coupon(
        id=uuid.UUID(int=10),
        user_id=USER_ID,
        game_id=uuid.UUID(int=11),
        game_type_id=uuid.UUID(int=12),
        numbers=[1, 2, 3, 4, 5, 6],
        is_quick_pick=True,
        price=10,
    )

    assert session.added == [coupon]


async def test_get_coupon_selects_coupon_by_id() -> None:
    session = FakeSession(coupons=[])
    expected = [
        (
            f"SELECT {COUPON_COLUMNS} FROM coupons"
            " WHERE coupons.id = '00000000-0000-0000-0000-00000000000a'"
        )
    ]

    await make_database(session).get_coupon(uuid.UUID(int=10))

    assert [compile_sql(s) for s in session.statements] == expected


async def test_get_coupon_returns_coupon() -> None:
    coupon = make_coupon()

    result = await make_database(FakeSession(coupons=[coupon])).get_coupon(coupon.id)

    assert result is coupon


async def test_get_coupon_returns_none_for_unknown_id() -> None:
    result = await make_database(FakeSession(coupons=[])).get_coupon(uuid.uuid4())

    assert result is None
