import os
from functools import lru_cache

from .broker import MessageBroker
from .db import Database

DEFAULT_DATABASE_URL = "postgresql+asyncpg://lotto:lotto@localhost:5432/lotto"
DEFAULT_BROKER_URL = "amqp://guest:guest@localhost:5672/"


class Connectors:
    db: Database
    broker: MessageBroker

    def __init__(self) -> None:
        self.db = Database(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        self.broker = MessageBroker(os.environ.get("BROKER_URL", DEFAULT_BROKER_URL))


@lru_cache(maxsize=1)
def get_connectors_object() -> Connectors:
    return Connectors()


def get_database() -> Database:
    return get_connectors_object().db


def get_broker() -> MessageBroker:
    return get_connectors_object().broker
