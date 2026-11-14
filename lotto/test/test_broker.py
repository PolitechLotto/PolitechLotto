import json
from typing import Any

import aio_pika
import pytest

from lotto.connectors.broker import EVENTS_EXCHANGE, MessageBroker


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
) -> list[tuple[str, FakeConnection]]:
    opened: list[tuple[str, FakeConnection]] = []

    async def connect_robust(url: str, **_: Any) -> FakeConnection:
        connection = FakeConnection(channel)
        opened.append((url, connection))
        return connection

    monkeypatch.setattr(aio_pika, "connect_robust", connect_robust)
    return opened


async def test_publish_sends_persistent_json_message(
    exchange: FakeExchange,
    channel: FakeChannel,
    connections: list[tuple[str, FakeConnection]],
) -> None:
    broker = MessageBroker("amqp://test/")

    await broker.publish("game.created", {"game_id": "abc", "jackpot": 1000})

    assert [url for url, _ in connections] == ["amqp://test/"]
    assert channel.declared == [(EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, True)]
    message, routing_key = exchange.published[0]
    assert routing_key == "game.created"
    assert json.loads(message.body) == {"game_id": "abc", "jackpot": 1000}
    assert message.content_type == "application/json"
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT


async def test_publish_reuses_connection(
    exchange: FakeExchange, connections: list[tuple[str, FakeConnection]]
) -> None:
    broker = MessageBroker("amqp://test/")

    await broker.publish("a", {})
    await broker.publish("b", {})

    assert len(connections) == 1
    assert [key for _, key in exchange.published] == ["a", "b"]


async def test_close_closes_connection_and_allows_reconnect(
    connections: list[tuple[str, FakeConnection]],
) -> None:
    broker = MessageBroker("amqp://test/")
    await broker.publish("a", {})

    await broker.close()
    await broker.publish("b", {})

    assert connections[0][1].closed
    assert len(connections) == 2


async def test_close_without_connection_does_nothing() -> None:
    await MessageBroker("amqp://test/").close()
