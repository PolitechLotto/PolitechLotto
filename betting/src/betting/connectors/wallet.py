import os
import uuid
from http import HTTPStatus

import httpx

from betting.exceptions import InsufficientFunds, UpstreamError

DEFAULT_WALLET_URL = "http://wallet:8000/internal"


class WalletClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=os.environ.get("WALLET_URL", DEFAULT_WALLET_URL), timeout=5.0
        )

    async def charge(
        self, user_id: uuid.UUID, amount: int, reference_id: uuid.UUID
    ) -> None:
        """Safe to retry: wallet charges each `reference_id` at most once."""
        try:
            response = await self._client.post(
                f"/v1/wallets/{user_id}:charge",
                json={"amount": amount, "reference_id": str(reference_id)},
            )
        except httpx.HTTPError as error:
            raise UpstreamError("wallet") from error
        if response.status_code == HTTPStatus.CONFLICT:
            raise InsufficientFunds
        if response.status_code != HTTPStatus.OK:
            raise UpstreamError("wallet")

    async def close(self) -> None:
        await self._client.aclose()
