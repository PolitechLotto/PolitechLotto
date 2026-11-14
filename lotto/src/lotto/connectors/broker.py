import asyncio
import json
from typing import Any

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

EVENTS_EXCHANGE = "events"


class MessageBroker:
    def __init__(self, url: str, exchange_name: str = EVENTS_EXCHANGE) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None
        self._lock = asyncio.Lock()

    async def _get_exchange(self) -> AbstractExchange:
        async with self._lock:
            if self._exchange is None:
                self._connection = await aio_pika.connect_robust(self._url)
                channel = await self._connection.channel()
                self._exchange = await channel.declare_exchange(
                    self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
                )
            return self._exchange

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        exchange = await self._get_exchange()
        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await exchange.publish(message, routing_key=routing_key)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._exchange = None
