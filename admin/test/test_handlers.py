import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, call

from admin.connectors.models import AdminActionType, TargetType
from admin.handlers.handlers_v1 import (
    AdminActionsPage,
    AdminActionView,
    list_admin_actions_handler,
)

from .factories import make_admin_action


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
