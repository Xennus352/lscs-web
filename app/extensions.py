import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.security import HTTPBearer

REDIS_URL = os.getenv("REDIS_URL")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL if REDIS_URL else "memory://",
    key_prefix="lbvd",
)

security = HTTPBearer()