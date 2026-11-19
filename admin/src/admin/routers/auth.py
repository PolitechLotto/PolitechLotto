import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Header, HTTPException

ADMIN_ROLE = "admin"


async def require_admin(
    x_user_id: Annotated[str | None, Header()] = None,
    x_user_roles: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """Returns the caller's user ID from the headers set by the gateway.

    401 when the request carries no valid identity, 403 when the caller is not an admin.
    """
    try:
        user_id = uuid.UUID(x_user_id or "")
    except ValueError:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, detail="Not authenticated."
        ) from None
    roles = {role.strip() for role in (x_user_roles or "").split(",")}
    if ADMIN_ROLE not in roles:
        raise HTTPException(HTTPStatus.FORBIDDEN, detail="Admin role required.")
    return user_id


AdminId = Annotated[uuid.UUID, Depends(require_admin)]
