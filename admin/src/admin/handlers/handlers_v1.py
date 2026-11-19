import uuid
from dataclasses import dataclass
from datetime import datetime

from admin.connectors.db import Database
from admin.connectors.models import AdminAction, AdminActionType, TargetType


async def example_handler(database: Database) -> int:
    return await database.get_random_int()


@dataclass(frozen=True)
class AdminActionView:
    id: uuid.UUID
    admin_id: uuid.UUID
    action: AdminActionType
    target_type: TargetType
    target_id: uuid.UUID
    description: str
    created_at: datetime


@dataclass(frozen=True)
class AdminActionsPage:
    items: list[AdminActionView]
    total: int


def _admin_action_view(action: AdminAction) -> AdminActionView:
    return AdminActionView(
        id=action.id,
        admin_id=action.admin_id,
        action=action.action,
        target_type=action.target_type,
        target_id=action.target_id,
        description=action.description,
        created_at=action.created_at,
    )


async def list_admin_actions_handler(
    database: Database,
    action: AdminActionType | None,
    target_type: TargetType | None,
    admin_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    offset: int,
) -> AdminActionsPage:
    actions, total = await database.list_admin_actions(
        action=action,
        target_type=target_type,
        admin_id=admin_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return AdminActionsPage(
        items=[_admin_action_view(admin_action) for admin_action in actions],
        total=total,
    )
