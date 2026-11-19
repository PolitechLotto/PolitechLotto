from random import randint


class Database:
    async def get_random_int(self) -> int:
        return randint(0, 10)
