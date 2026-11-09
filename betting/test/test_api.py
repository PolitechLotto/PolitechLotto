from collections.abc import AsyncIterator

import httpx
import pytest

from betting.main import create_sub_app
from betting.routers.api_v1 import router

app = create_sub_app(title="API", routers=[router])
prefix = ""


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
