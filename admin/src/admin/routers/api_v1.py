import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict

from admin.connectors import get_database
from admin.connectors.db import Database
from admin.connectors.models import AdminActionType, TargetType
from admin.handlers.handlers_v1 import list_admin_actions_handler
from admin.routers.auth import require_admin

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
