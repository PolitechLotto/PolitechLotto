from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Response, status

from .connectors import get_connectors_object
from .routers.api_v1 import router


def create_sub_app(
    title: str,
    routers: Iterable[APIRouter],
    extra_fastapi_args: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI(title=title, **(extra_fastapi_args or {}))
    for api_router in routers:
        app.include_router(api_router)
    return app


def create_app(
    lifespan: Any,
    title: str,
    router_prefix: str | None = None,
    *,
    include_health_checks: bool = True,
    extra_fastapi_args: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI(title=title, lifespan=lifespan, **(extra_fastapi_args or {}))

    if include_health_checks:

        @app.get("/health/alive", description="Health check endpoint.")
        async def health_alive() -> Response:
            return Response(status_code=status.HTTP_200_OK)

    return app


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator:
    connectors = get_connectors_object()
    yield
    await connectors.db.close()


app = create_app(lifespan=lifespan, title="lotto")
app.mount("/api/", create_sub_app(title="API", routers=[router]))
