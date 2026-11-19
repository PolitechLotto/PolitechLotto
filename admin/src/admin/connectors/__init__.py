from functools import lru_cache

from .db import Database
from .services import AuthClient, BettingClient, LottoClient, WalletClient


class Connectors:
    db: Database
    lotto: LottoClient
    betting: BettingClient
    auth: AuthClient
    wallet: WalletClient

    def __init__(self) -> None:
        self.db = Database()
        self.lotto = LottoClient()
        self.betting = BettingClient()
        self.auth = AuthClient()
        self.wallet = WalletClient()


@lru_cache(maxsize=1)
def get_connectors_object() -> Connectors:
    return Connectors()


def get_database() -> Database:
    return get_connectors_object().db


def get_lotto_client() -> LottoClient:
    return get_connectors_object().lotto


def get_betting_client() -> BettingClient:
    return get_connectors_object().betting


def get_auth_client() -> AuthClient:
    return get_connectors_object().auth


def get_wallet_client() -> WalletClient:
    return get_connectors_object().wallet
