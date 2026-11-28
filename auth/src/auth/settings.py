import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

logger = logging.getLogger(__name__)

DEV_JWT_SECRET = "politechlotto-dev-secret-change-me-in-production"


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "politechlotto-auth"
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=30)
    online_window: timedelta = timedelta(minutes=5)
    """A user is online when they were last seen within this window."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        logger.warning("JWT_SECRET is not set, using an insecure development secret")
        secret = DEV_JWT_SECRET
    return Settings(
        jwt_secret=secret,
        access_token_ttl=timedelta(
            minutes=int(os.environ.get("ACCESS_TOKEN_TTL_MINUTES", "15"))
        ),
        refresh_token_ttl=timedelta(
            days=int(os.environ.get("REFRESH_TOKEN_TTL_DAYS", "30"))
        ),
    )
