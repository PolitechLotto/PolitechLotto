import os
import uuid
from datetime import datetime
from http import HTTPStatus

import httpx
from pydantic import BaseModel, ValidationError

from betting.exceptions import GameNotFound, UpstreamError

DEFAULT_LOTTO_URL = "http://lotto:8000/api"


class LottoGameType(BaseModel):
    id: uuid.UUID
    number_pool_size: int
    number_pick_count: int


class LottoGame(BaseModel):
    id: uuid.UUID
    game_type_id: uuid.UUID
    ticket_price: int
    status: str
    scheduled_at: datetime
    started_at: datetime | None
    game_type: LottoGameType


class LottoClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=os.environ.get("LOTTO_URL", DEFAULT_LOTTO_URL), timeout=5.0
        )

    async def get_game(self, game_id: uuid.UUID) -> LottoGame:
        try:
            response = await self._client.get(f"/v1/games/{game_id}")
        except httpx.HTTPError as error:
            raise UpstreamError("lotto") from error
        if response.status_code == HTTPStatus.NOT_FOUND:
            raise GameNotFound
        if response.status_code != HTTPStatus.OK:
            raise UpstreamError("lotto")
        try:
            return LottoGame.model_validate_json(response.content)
        except ValidationError as error:
            raise UpstreamError("lotto") from error

    async def close(self) -> None:
        await self._client.aclose()
