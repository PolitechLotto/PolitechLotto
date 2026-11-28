from http import HTTPStatus
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from auth.connectors import get_broker, get_database
from auth.connectors.broker import MessageBroker
from auth.connectors.db import Database
from auth.connectors.models import UserStatus
from auth.handlers.handlers_v1 import (
    CannotDeleteSelfError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenIn,
    TokenCreate,
    TokenOut,
    UserCreate,
    UserNotFoundError,
    UserOut,
    UsersBatch,
    UsersPage,
    UserTakenError,
    batch_get_users_handler,
    delete_user_handler,
    get_current_user_handler,
    get_user_handler,
    list_users_handler,
    login_handler,
    refresh_token_handler,
    register_user_handler,
    revoke_token_handler,
)
from auth.routers.identity import AdminId, UserId
from auth.settings import Settings, get_settings

router = APIRouter(prefix="/v1")

DatabaseDep = Annotated[Database, Depends(get_database)]
BrokerDep = Annotated[MessageBroker, Depends(get_broker)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

MAX_BATCH_SIZE = 100

Responses = dict[int | str, dict[str, Any]]

UNAUTHORIZED: Responses = {
    HTTPStatus.UNAUTHORIZED: {"description": "Not authenticated"}
}
ADMIN_ONLY: Responses = {
    **UNAUTHORIZED,
    HTTPStatus.FORBIDDEN: {"description": "The caller is not an admin"},
}
NOT_FOUND: Responses = {HTTPStatus.NOT_FOUND: {"description": "User not found"}}


def _not_found(e: Exception) -> HTTPException:
    return HTTPException(HTTPStatus.NOT_FOUND, detail=str(e))


@router.post(
    "/users",
    status_code=HTTPStatus.CREATED,
    description="Registers a new player account.",
    responses={HTTPStatus.CONFLICT: {"description": "Email or username taken"}},
)
async def register_user(
    data: UserCreate,
    database: DatabaseDep,
    broker: BrokerDep,
    settings: SettingsDep,
) -> UserOut:
    try:
        return await register_user_handler(database, broker, settings, data)
    except UserTakenError as e:
        raise HTTPException(HTTPStatus.CONFLICT, detail=str(e)) from e


@router.post(
    "/token",
    description="Logs in with an email or username and a password.",
    responses={HTTPStatus.UNAUTHORIZED: {"description": "Invalid credentials"}},
)
async def create_token(
    data: TokenCreate, database: DatabaseDep, settings: SettingsDep
) -> TokenOut:
    try:
        return await login_handler(database, settings, data)
    except InvalidCredentialsError as e:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, detail=str(e)) from e


@router.post(
    "/token:refresh",
    description="Exchanges a refresh token for a new token pair. The old refresh token "
    "stops working.",
    responses={HTTPStatus.UNAUTHORIZED: {"description": "Invalid refresh token"}},
)
async def refresh_token(
    data: RefreshTokenIn, database: DatabaseDep, settings: SettingsDep
) -> TokenOut:
    try:
        return await refresh_token_handler(database, settings, data)
    except InvalidRefreshTokenError as e:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, detail=str(e)) from e


@router.post(
    "/token:revoke",
    status_code=HTTPStatus.NO_CONTENT,
    description="Revokes a refresh token (logout). Succeeds for unknown tokens too.",
)
async def revoke_token(data: RefreshTokenIn, database: DatabaseDep) -> Response:
    await revoke_token_handler(database, data)
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.get(
    "/users/me",
    description="Returns the logged in user.",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
async def get_current_user(
    user_id: UserId, database: DatabaseDep, settings: SettingsDep
) -> UserOut:
    try:
        return await get_current_user_handler(database, settings, user_id)
    except UserNotFoundError as e:
        raise _not_found(e) from e


@router.get(
    "/users",
    description="Lists users that are not deleted, newest first. Admin only.",
    responses=ADMIN_ONLY,
)
async def list_users(
    _: AdminId,
    database: DatabaseDep,
    settings: SettingsDep,
    status: UserStatus = UserStatus.ALL,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UsersPage:
    return await list_users_handler(database, settings, status, limit, offset)


@router.get(
    "/users:batchGet",
    description="Returns the users with the given IDs, deleted ones included. Unknown "
    "IDs are skipped. Admin only.",
    responses=ADMIN_ONLY,
)
async def batch_get_users(
    _: AdminId,
    database: DatabaseDep,
    settings: SettingsDep,
    ids: Annotated[list[UUID], Query(min_length=1, max_length=MAX_BATCH_SIZE)],
) -> UsersBatch:
    return await batch_get_users_handler(database, settings, ids)


@router.get(
    "/users/{user_id}",
    description="Returns one user, deleted or not. Admin only.",
    responses={**ADMIN_ONLY, **NOT_FOUND},
)
async def get_user(
    user_id: UUID, _: AdminId, database: DatabaseDep, settings: SettingsDep
) -> UserOut:
    try:
        return await get_user_handler(database, settings, user_id)
    except UserNotFoundError as e:
        raise _not_found(e) from e


@router.delete(
    "/users/{user_id}",
    status_code=HTTPStatus.NO_CONTENT,
    description="Deletes a user: removes their personal data and logs them out. "
    "Admin only.",
    responses={
        **ADMIN_ONLY,
        **NOT_FOUND,
        HTTPStatus.CONFLICT: {"description": "An admin tried to delete themselves"},
    },
)
async def delete_user(
    user_id: UUID, admin_id: AdminId, database: DatabaseDep, broker: BrokerDep
) -> Response:
    try:
        await delete_user_handler(database, broker, user_id, admin_id)
    except UserNotFoundError as e:
        raise _not_found(e) from e
    except CannotDeleteSelfError as e:
        raise HTTPException(HTTPStatus.CONFLICT, detail=str(e)) from e
    return Response(status_code=HTTPStatus.NO_CONTENT)
