"""The caller's identity, read from the headers set by the gateway after it verifies the
access token (ADR 004). The gateway must strip these headers from incoming requests."""

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from auth.connectors.models import UserRole


def require_user(
    x_user_id: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """401 when the request carries no valid identity."""
    try:
        return uuid.UUID(x_user_id or "")
    except ValueError:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, detail="Not authenticated."
        ) from None


def require_admin(
    user_id: Annotated[uuid.UUID, Depends(require_user)],
    x_user_roles: Annotated[str | None, Header()] = None,
    x_user_role: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """401 when the request carries no valid identity, 403 when the caller is not an
    admin. Accepts both `X-User-Roles` (comma-separated) and `X-User-Role`."""
    roles = {
        role.strip()
        for header in (x_user_roles, x_user_role)
        for role in (header or "").split(",")
    }
    if UserRole.ADMIN not in roles:
        raise HTTPException(HTTPStatus.FORBIDDEN, detail="Admin role required.")
    return user_id


UserId = Annotated[uuid.UUID, Depends(require_user)]
AdminId = Annotated[uuid.UUID, Depends(require_admin)]
