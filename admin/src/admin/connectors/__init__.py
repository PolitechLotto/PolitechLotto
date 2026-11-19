from functools import lru_cache

from .db import Database


class Connectors:
    db: Database

    def __init__(self) -> None:
        self.db = Database()


@lru_cache(maxsize=1)
def get_connectors_object() -> Connectors:
    return Connectors()


def get_database() -> Database:
    return get_connectors_object().db
