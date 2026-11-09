import json
import uuid
from collections.abc import Callable

import httpx
import pytest

from betting.connectors.wallet import WalletClient
from betting.exceptions import InsufficientFunds, UpstreamError

USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
COUPON_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> WalletClient:
    return WalletClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://wallet/internal"
        )
    )


async def test_charge_posts_amount_and_reference() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"balance": 90})

    expected = [
        (
            "POST",
            f"http://wallet/internal/v1/wallets/{USER_ID}:charge",
            {"amount": 10, "reference_id": str(COUPON_ID)},
        )
    ]

    await make_client(handler).charge(USER_ID, amount=10, reference_id=COUPON_ID)

    assert [(r.method, str(r.url), json.loads(r.content)) for r in requests] == (
        expected
    )


async def test_charge_raises_insufficient_funds_for_409() -> None:
    client = make_client(lambda _: httpx.Response(409))

    with pytest.raises(InsufficientFunds):
        await client.charge(USER_ID, amount=10, reference_id=COUPON_ID)


def raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timeout", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(404),
        lambda _: httpx.Response(500),
        raise_timeout,
    ],
    ids=["wallet-missing", "server-error", "timeout"],
)
async def test_charge_raises_upstream_error_on_failure(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(UpstreamError):
        await make_client(handler).charge(USER_ID, amount=10, reference_id=COUPON_ID)
