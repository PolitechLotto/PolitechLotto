from fastapi import APIRouter

from lotto.connectors import get_database
from lotto.handlers.handlers_v1 import example_handler

router = APIRouter(prefix="/v1")


@router.get("/")
async def example() -> dict[str, int]:
    handler_output = await example_handler(get_database())
    return {"output": handler_output}
