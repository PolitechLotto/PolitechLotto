import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, call

import pytest

from admin.connectors.models import AdminActionType, Report, ReportType, TargetType
from admin.connectors.services import (
    AuthUser,
    CouponStatsByDay,
    CouponStatsByGameType,
    CouponStatsByUser,
    GamesPlayedByDay,
    GamesPlayedByGameType,
    ServiceError,
)
from admin.handlers.handlers_v1 import (
    AdminActionsPage,
    AdminActionView,
    DailySummaryRowView,
    GameStatsRowView,
    InvalidReportPeriodError,
    ReportDetailsView,
    ReportRowView,
    ReportsPage,
    ReportView,
    UserActivityRowView,
    create_report_handler,
    get_report_handler,
    list_admin_actions_handler,
    list_reports_handler,
)

from .factories import make_admin_action, make_game_stats_row, make_report


async def test_list_admin_actions_passes_filters_to_database() -> None:
    database = AsyncMock()
    database.list_admin_actions.return_value = ([], 0)
    admin_id = uuid.uuid4()
    created_from = datetime(2026, 11, 1, tzinfo=UTC)
    created_to = datetime(2026, 11, 30, tzinfo=UTC)
    expected = [
        call(
            action=AdminActionType.USER_DELETED,
            target_type=TargetType.USER,
            admin_id=admin_id,
            created_from=created_from,
            created_to=created_to,
            limit=10,
            offset=20,
        )
    ]

    await list_admin_actions_handler(
        database,
        action=AdminActionType.USER_DELETED,
        target_type=TargetType.USER,
        admin_id=admin_id,
        created_from=created_from,
        created_to=created_to,
        limit=10,
        offset=20,
    )

    assert database.list_admin_actions.await_args_list == expected


async def test_list_admin_actions_returns_page_of_views() -> None:
    action = make_admin_action()
    database = AsyncMock()
    database.list_admin_actions.return_value = ([action], 42)
    expected = AdminActionsPage(
        items=[
            AdminActionView(
                id=action.id,
                admin_id=action.admin_id,
                action=action.action,
                target_type=action.target_type,
                target_id=action.target_id,
                description=action.description,
                created_at=action.created_at,
            )
        ],
        total=42,
    )

    page = await list_admin_actions_handler(
        database, None, None, None, None, None, 50, 0
    )

    assert page == expected


ADMIN_ID = uuid.UUID(int=99)
REPORT_ID = uuid.UUID(int=500)
GAME_TYPE_A = uuid.UUID(int=1)
GAME_TYPE_B = uuid.UUID(int=2)
USER_A = uuid.UUID(int=11)
USER_B = uuid.UUID(int=12)
CREATED_AT = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
LAST_SEEN_AT = datetime(2026, 11, 18, 19, 45, tzinfo=UTC)

Clients = tuple[AsyncMock, AsyncMock, AsyncMock]


def make_report_database() -> AsyncMock:
    """create_report returns a report built from its arguments."""

    async def create_report(
        admin_id: uuid.UUID,
        report_type: ReportType,
        period_from: date,
        period_to: date,
        rows: list,
    ) -> Report:
        return Report(
            id=REPORT_ID,
            created_by=admin_id,
            type=report_type,
            period_from=period_from,
            period_to=period_to,
            created_at=CREATED_AT,
        )

    database = AsyncMock()
    database.create_report.side_effect = create_report
    return database


def make_clients() -> Clients:
    lotto, betting, auth = AsyncMock(), AsyncMock(), AsyncMock()
    lotto.games_by_day.return_value = [
        GamesPlayedByDay(day=date(2026, 11, 2), games_played=3),
        GamesPlayedByDay(day=date(2026, 11, 1), games_played=4),
    ]
    betting.coupon_stats_by_day.return_value = [
        CouponStatsByDay(
            day=date(2026, 11, 1),
            coupons_sold=24,
            points_spent=240,
            points_awarded=100,
            active_players=3,
        )
    ]
    lotto.games_by_game_type.return_value = [
        GamesPlayedByGameType(game_type_id=GAME_TYPE_A, games_played=8),
        GamesPlayedByGameType(game_type_id=GAME_TYPE_B, games_played=4),
    ]
    betting.coupon_stats_by_game_type.return_value = [
        CouponStatsByGameType(
            game_type_id=GAME_TYPE_B,
            coupons_sold=50,
            points_spent=500,
            points_awarded=200,
        )
    ]
    betting.coupon_stats_by_user.return_value = [
        CouponStatsByUser(
            user_id=USER_A, coupons_sold=2, points_spent=20, points_awarded=0
        ),
        CouponStatsByUser(
            user_id=USER_B, coupons_sold=30, points_spent=300, points_awarded=150
        ),
    ]
    auth.get_users.return_value = [
        AuthUser(
            id=USER_B,
            username="szczesciarz",
            email="szczesciarz@example.com",
            role="player",
            created_at=CREATED_AT,
            last_login_at=CREATED_AT,
            last_seen_at=LAST_SEEN_AT,
            is_online=True,
        )
    ]
    return lotto, betting, auth


async def create_report(
    database: AsyncMock,
    report_type: ReportType,
    period_from: date = date(2026, 11, 1),
    period_to: date = date(2026, 11, 30),
    clients: Clients | None = None,
) -> ReportDetailsView:
    lotto, betting, auth = clients or make_clients()
    return await create_report_handler(
        database,
        lotto,
        betting,
        auth,
        ADMIN_ID,
        report_type,
        period_from,
        period_to,
    )


def expected_report(
    report_type: ReportType, rows: list[ReportRowView]
) -> ReportDetailsView:
    return ReportDetailsView(
        id=REPORT_ID,
        type=report_type,
        period_from=date(2026, 11, 1),
        period_to=date(2026, 11, 30),
        created_by=ADMIN_ID,
        created_at=CREATED_AT,
        rows=rows,
    )


async def test_create_daily_summary_merges_games_and_coupons_by_day() -> None:
    expected = expected_report(
        ReportType.DAILY_SUMMARY,
        [
            DailySummaryRowView(
                day=date(2026, 11, 1),
                games_played=4,
                active_players=3,
                points_spent=240,
                points_awarded=100,
            ),
            DailySummaryRowView(
                day=date(2026, 11, 2),
                games_played=3,
                active_players=0,
                points_spent=0,
                points_awarded=0,
            ),
        ],
    )

    report = await create_report(make_report_database(), ReportType.DAILY_SUMMARY)

    assert report == expected


async def test_create_game_stats_merges_by_game_type_most_coupons_first() -> None:
    expected = expected_report(
        ReportType.GAME_STATS,
        [
            GameStatsRowView(
                game_type_id=GAME_TYPE_B,
                games_played=4,
                coupons_sold=50,
                points_spent=500,
                points_awarded=200,
            ),
            GameStatsRowView(
                game_type_id=GAME_TYPE_A,
                games_played=8,
                coupons_sold=0,
                points_spent=0,
                points_awarded=0,
            ),
        ],
    )

    report = await create_report(make_report_database(), ReportType.GAME_STATS)

    assert report == expected


async def test_create_user_activity_adds_last_seen_from_auth() -> None:
    clients = make_clients()
    expected = expected_report(
        ReportType.USER_ACTIVITY,
        [
            UserActivityRowView(
                user_id=USER_B,
                coupons_bought=30,
                points_spent=300,
                points_won=150,
                last_seen_at=LAST_SEEN_AT,
            ),
            UserActivityRowView(
                user_id=USER_A,
                coupons_bought=2,
                points_spent=20,
                points_won=0,
                last_seen_at=None,
            ),
        ],
    )

    report = await create_report(
        make_report_database(), ReportType.USER_ACTIVITY, clients=clients
    )

    assert (report, clients[2].get_users.await_args_list) == (
        expected,
        [call([USER_A, USER_B])],
    )


async def test_create_report_saves_the_collected_rows() -> None:
    database = make_report_database()

    await create_report(database, ReportType.DAILY_SUMMARY)

    args = database.create_report.await_args.args
    assert args[:4] == (
        ADMIN_ID,
        ReportType.DAILY_SUMMARY,
        date(2026, 11, 1),
        date(2026, 11, 30),
    )
    assert [(row.day, row.games_played, row.points_spent) for row in args[4]] == [
        (date(2026, 11, 1), 4, 240),
        (date(2026, 11, 2), 3, 0),
    ]


async def test_create_report_passes_period_to_services() -> None:
    lotto, betting, auth = make_clients()

    await create_report(
        make_report_database(), ReportType.GAME_STATS, clients=(lotto, betting, auth)
    )

    period = call(date(2026, 11, 1), date(2026, 11, 30))
    assert (
        lotto.games_by_game_type.await_args_list,
        betting.coupon_stats_by_game_type.await_args_list,
    ) == ([period], [period])


async def test_create_report_accepts_the_longest_period() -> None:
    database = make_report_database()

    await create_report(
        database, ReportType.GAME_STATS, date(2028, 1, 1), date(2028, 12, 31)
    )

    assert database.create_report.await_count == 1


@pytest.mark.parametrize(
    ("period_from", "period_to", "message"),
    [
        (date(2026, 11, 2), date(2026, 11, 1), "period_from is after period_to."),
        (date(2026, 1, 1), date(2027, 1, 2), "The period is longer than 366 days."),
    ],
)
async def test_create_report_rejects_invalid_period(
    period_from: date, period_to: date, message: str
) -> None:
    database = make_report_database()
    lotto, betting, auth = make_clients()

    with pytest.raises(InvalidReportPeriodError, match=message):
        await create_report(
            database,
            ReportType.DAILY_SUMMARY,
            period_from,
            period_to,
            clients=(lotto, betting, auth),
        )

    assert (database.create_report.await_count, lotto.games_by_day.await_count) == (
        0,
        0,
    )


async def test_create_report_does_not_save_when_a_service_fails() -> None:
    database = make_report_database()
    lotto, betting, auth = make_clients()
    betting.coupon_stats_by_day.side_effect = ServiceError("betting is down")

    with pytest.raises(ServiceError):
        await create_report(
            database, ReportType.DAILY_SUMMARY, clients=(lotto, betting, auth)
        )

    assert database.create_report.await_count == 0


async def test_list_reports_passes_filter_to_database() -> None:
    database = AsyncMock()
    database.list_reports.return_value = ([], 0)

    await list_reports_handler(database, ReportType.USER_ACTIVITY, 10, 20)

    assert database.list_reports.await_args_list == [
        call(ReportType.USER_ACTIVITY, 10, 20)
    ]


async def test_list_reports_returns_page_of_views_without_rows() -> None:
    report = make_report()
    database = AsyncMock()
    database.list_reports.return_value = ([report], 9)
    expected = ReportsPage(
        items=[
            ReportView(
                id=report.id,
                type=report.type,
                period_from=report.period_from,
                period_to=report.period_to,
                created_by=report.created_by,
                created_at=report.created_at,
            )
        ],
        total=9,
    )

    page = await list_reports_handler(database, None, 50, 0)

    assert page == expected


async def test_get_report_passes_id_to_database() -> None:
    database = AsyncMock()
    database.get_report.return_value = None

    await get_report_handler(database, REPORT_ID)

    assert database.get_report.await_args_list == [call(REPORT_ID)]


async def test_get_report_returns_report_with_rows() -> None:
    report = make_report(id=REPORT_ID, created_by=ADMIN_ID, created_at=CREATED_AT)
    row = make_game_stats_row(game_type_id=GAME_TYPE_A)
    database = AsyncMock()
    database.get_report.return_value = (report, [row])
    expected = ReportDetailsView(
        id=REPORT_ID,
        type=report.type,
        period_from=date(2026, 11, 1),
        period_to=date(2026, 11, 30),
        created_by=ADMIN_ID,
        created_at=CREATED_AT,
        rows=[
            GameStatsRowView(
                game_type_id=GAME_TYPE_A,
                games_played=4,
                coupons_sold=48,
                points_spent=480,
                points_awarded=150,
            )
        ],
    )

    view = await get_report_handler(database, REPORT_ID)

    assert view == expected


async def test_get_report_returns_none_for_unknown_id() -> None:
    database = AsyncMock()
    database.get_report.return_value = None

    view = await get_report_handler(database, REPORT_ID)

    assert view is None
