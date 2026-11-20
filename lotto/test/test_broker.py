import json
from typing import Any

import aio_pika
import pytest

from lotto.connectors.broker import EVENTS_EXCHANGE, MessageBroker

BROKER_URL = "amqp://test/"
ROUTING_KEY = "game.created"
OTHER_ROUTING_KEY = "game.finished"
PAYLOAD = {"game_id": "abc", "jackpot": 1000}


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[aio_pika.Message, str]] = []

    async def publish(self, message: aio_pika.Message, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeChannel:
    def __init__(self, exchange: FakeExchange) -> None:
        self.exchange = exchange
        self.declared: list[tuple[str, aio_pika.ExchangeType, bool]] = []

    async def declare_exchange(
        self, name: str, type: aio_pika.ExchangeType, durable: bool
    ) -> FakeExchange:
        self.declared.append((name, type, durable))
        return self.exchange


class FakeConnection:
    def __init__(self, channel: FakeChannel) -> None:
        self._channel = channel
        self.closed = False

    async def channel(self) -> FakeChannel:
        return self._channel

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def exchange() -> FakeExchange:
    return FakeExchange()


@pytest.fixture
def channel(exchange: FakeExchange) -> FakeChannel:
    return FakeChannel(exchange)


@pytest.fixture
def connections(
    monkeypatch: pytest.MonkeyPatch, channel: FakeChannel
) -> list[FakeConnection]:
    opened: list[FakeConnection] = []

    async def connect_robust(url: str, **_: Any) -> FakeConnection:
        assert url == BROKER_URL
        connection = FakeConnection(channel)
        opened.append(connection)
        return connection

    monkeypatch.setattr(aio_pika, "connect_robust", connect_robust)
    return opened


async def test_publish_sends_persistent_json_message_to_events_exchange(
    exchange: FakeExchange,
    channel: FakeChannel,
    connections: list[FakeConnection],
) -> None:
    broker = MessageBroker(BROKER_URL)

    await broker.publish(ROUTING_KEY, PAYLOAD)

    message, routing_key = exchange.published[0]
    assert channel.declared == [(EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, True)]
    assert routing_key == ROUTING_KEY
    assert json.loads(message.body) == PAYLOAD
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT


async def test_publish_reuses_connection(
    exchange: FakeExchange, connections: list[FakeConnection]
) -> None:
    broker = MessageBroker(BROKER_URL)

    await broker.publish(ROUTING_KEY, PAYLOAD)
    await broker.publish(OTHER_ROUTING_KEY, PAYLOAD)

    assert len(connections) == 1
    assert len(exchange.published) == 2


async def test_close_closes_connection_and_allows_reconnect(
    connections: list[FakeConnection],
) -> None:
    broker = MessageBroker(BROKER_URL)
    await broker.publish(ROUTING_KEY, PAYLOAD)

    await broker.close()
    await broker.publish(ROUTING_KEY, PAYLOAD)

    assert connections[0].closed
    assert len(connections) == 2
