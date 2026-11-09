import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from betting.connectors.lotto import LottoClient, LottoGame, LottoGameType
from betting.exceptions import GameNotFound, UpstreamError

GAME_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
GAME_TYPE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

GAME_JSON = {
    "id": str(GAME_ID),
    "name": "6 z 49",
    "game_type_id": str(GAME_TYPE_ID),
    "ticket_price": 10,
    "jackpot": 1000,
    "status": "scheduled",
    "scheduled_at": "2026-11-10T18:00:00Z",
    "started_at": None,
    "finished_at": None,
    "seed_hash": "hash",
    "seed": None,
    "winning_numbers": None,
    "game_type": {
        "id": str(GAME_TYPE_ID),
        "name": "6 z 49",
        "number_pool_size": 49,
        "number_pick_count": 6,
    },
}


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> LottoClient:
    return LottoClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://lotto/api"
        )
    )


async def test_get_game_requests_game_by_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=GAME_JSON)

    await make_client(handler).get_game(GAME_ID)

    assert [(r.method, str(r.url)) for r in requests] == [
        ("GET", f"http://lotto/api/v1/games/{GAME_ID}")
    ]


async def test_get_game_returns_game() -> None:
    expected = LottoGame(
        id=GAME_ID,
        game_type_id=GAME_TYPE_ID,
        ticket_price=10,
        status="scheduled",
        scheduled_at=datetime(2026, 11, 10, 18, 0, tzinfo=UTC),
        started_at=None,
        game_type=LottoGameType(
            id=GAME_TYPE_ID, number_pool_size=49, number_pick_count=6
        ),
    )

    game = await make_client(lambda _: httpx.Response(200, json=GAME_JSON)).get_game(
        GAME_ID
    )

    assert game == expected


async def test_get_game_raises_not_found_for_404() -> None:
    client = make_client(lambda _: httpx.Response(404, json={"detail": "x"}))

    with pytest.raises(GameNotFound):
        await client.get_game(GAME_ID)


def raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(200, json={"id": "not-a-game"}),
        lambda _: httpx.Response(200, content=b"not json"),
        raise_connect_error,
    ],
    ids=["server-error", "unexpected-shape", "invalid-json", "connection-error"],
)
async def test_get_game_raises_upstream_error_on_failure(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(UpstreamError):
        await make_client(handler).get_game(GAME_ID)
