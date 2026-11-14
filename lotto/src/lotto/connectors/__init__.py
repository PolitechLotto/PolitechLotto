import os
from functools import lru_cache

from .db import Database

DEFAULT_DATABASE_URL = "postgresql+asyncpg://lotto:lotto@localhost:5432/lotto"


class Connectors:
    db: Database

    def __init__(self) -> None:
        self.db = Database(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))


@lru_cache(maxsize=1)
def get_connectors_object() -> Connectors:
    return Connectors()


def get_database() -> Database:
    return get_connectors_object().db
