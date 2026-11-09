from functools import lru_cache

from .db import Database
from .lotto import LottoClient
from .wallet import WalletClient


class Connectors:
    db: Database
    lotto: LottoClient
    wallet: WalletClient

    def __init__(self) -> None:
        self.db = Database()
        self.lotto = LottoClient()
        self.wallet = WalletClient()

    async def close(self) -> None:
        await self.lotto.close()
        await self.wallet.close()


@lru_cache(maxsize=1)
def get_connectors_object() -> Connectors:
    return Connectors()


def get_database() -> Database:
    return get_connectors_object().db


def get_lotto() -> LottoClient:
    return get_connectors_object().lotto


def get_wallet() -> WalletClient:
    return get_connectors_object().wallet
