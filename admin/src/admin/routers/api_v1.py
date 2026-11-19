import uuid
from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict

from admin.connectors import (
    get_auth_client,
    get_betting_client,
    get_database,
    get_lotto_client,
    get_wallet_client,
)
from admin.connectors.db import Database
from admin.connectors.models import AdminActionType, ReportType, TargetType
from admin.connectors.services import (
    AuthClient,
    BettingClient,
    LottoClient,
    ServiceError,
    UserStatus,
    WalletClient,
)
from admin.handlers.handlers_v1 import (
    InvalidReportPeriodError,
    create_report_handler,
    get_report_handler,
    list_admin_actions_handler,
    list_players_handler,
    list_reports_handler,
)
from admin.routers.auth import AdminId, require_admin

router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(require_admin)],
    responses={
        HTTPStatus.UNAUTHORIZED: {"description": "No valid identity headers."},
        HTTPStatus.FORBIDDEN: {"description": "The caller is not an admin."},
    },
)


class AdminActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_id: uuid.UUID
    action: AdminActionType
    target_type: TargetType
    target_id: uuid.UUID
    description: str
    created_at: datetime


class AdminActionsPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[AdminActionResponse]
    total: int


@router.get("/actions", description="Lists the admin action log, newest first.")
async def list_admin_actions(
    database: Annotated[Database, Depends(get_database)],
    action: AdminActionType | None = None,
    target_type: TargetType | None = None,
    admin_id: uuid.UUID | None = None,
    created_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    created_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminActionsPageResponse:
    page = await list_admin_actions_handler(
        database,
        action=action,
        target_type=target_type,
        admin_id=admin_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return AdminActionsPageResponse.model_validate(page)


class CreateReportRequest(BaseModel):
    type: ReportType
    period_from: date
    period_to: date


class DailySummaryRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    games_played: int
    active_players: int
    points_spent: int
    points_awarded: int


class GameStatsRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    game_type_id: uuid.UUID
    games_played: int
    coupons_sold: int
    points_spent: int
    points_awarded: int


class UserActivityRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    coupons_bought: int
    points_spent: int
    points_won: int
    last_seen_at: datetime | None


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: ReportType
    period_from: date
    period_to: date
    created_by: uuid.UUID
    created_at: datetime


class ReportDetailsResponse(ReportResponse):
    rows: list[DailySummaryRowResponse | GameStatsRowResponse | UserActivityRowResponse]


@router.post(
    "/reports",
    status_code=HTTPStatus.CREATED,
    description="Generates a report from the statistics of the other services.",
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {
            "description": "Invalid body, period_from after period_to, or a period"
            " longer than 366 days."
        },
        HTTPStatus.BAD_GATEWAY: {"description": "Another service failed."},
    },
)
async def create_report(
    admin_id: AdminId,
    body: CreateReportRequest,
    database: Annotated[Database, Depends(get_database)],
    lotto: Annotated[LottoClient, Depends(get_lotto_client)],
    betting: Annotated[BettingClient, Depends(get_betting_client)],
    auth: Annotated[AuthClient, Depends(get_auth_client)],
) -> ReportDetailsResponse:
    try:
        report = await create_report_handler(
            database,
            lotto,
            betting,
            auth,
            admin_id=admin_id,
            report_type=body.type,
            period_from=body.period_from,
            period_to=body.period_to,
        )
    except InvalidReportPeriodError as error:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except ServiceError as error:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, detail="Another service failed."
        ) from error
    return ReportDetailsResponse.model_validate(report)


class ReportsPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ReportResponse]
    total: int


@router.get("/reports", description="Lists generated reports, newest first.")
async def list_reports(
    database: Annotated[Database, Depends(get_database)],
    report_type: Annotated[ReportType | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportsPageResponse:
    page = await list_reports_handler(
        database, report_type=report_type, limit=limit, offset=offset
    )
    return ReportsPageResponse.model_validate(page)


@router.get(
    "/reports/{report_id}",
    description="Returns one report with all its rows.",
    responses={HTTPStatus.NOT_FOUND: {"description": "Report not found."}},
)
async def get_report(
    database: Annotated[Database, Depends(get_database)],
    report_id: uuid.UUID,
) -> ReportDetailsResponse:
    report = await get_report_handler(database, report_id)
    if report is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="Report not found.")
    return ReportDetailsResponse.model_validate(report)


class PlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    username: str
    balance: int
    coupons_count: int
    is_online: bool
    last_login_at: datetime | None


class PlayersPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[PlayerResponse]
    total: int


@router.get(
    "/players",
    description="Lists players with their balances and coupon counts.",
    responses={HTTPStatus.BAD_GATEWAY: {"description": "Another service failed."}},
)
async def list_players(
    auth: Annotated[AuthClient, Depends(get_auth_client)],
    wallet: Annotated[WalletClient, Depends(get_wallet_client)],
    betting: Annotated[BettingClient, Depends(get_betting_client)],
    status: UserStatus = UserStatus.ALL,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlayersPageResponse:
    try:
        page = await list_players_handler(
            auth, wallet, betting, status=status, limit=limit, offset=offset
        )
    except ServiceError as error:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, detail="Another service failed."
        ) from error
    return PlayersPageResponse.model_validate(page)
