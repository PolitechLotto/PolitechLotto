from betting.connectors.db import Database


async def example_handler(database: Database) -> int:
    return await database.get_random_int()
