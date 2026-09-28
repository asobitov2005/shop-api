import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
VERSION_KEY = "products:list:version"


class ProductCache:
    def __init__(self, client: Redis) -> None:
        self.client = client

    def get(self, page: int, page_size: int) -> tuple[dict[str, Any] | None, str | None]:
        try:
            version = str(self.client.get(VERSION_KEY) or "0")
            key = f"products:list:v{version}:p{page}:s{page_size}"
            value = self.client.get(key)
            return (json.loads(value) if value is not None else None), version
        except (RedisError, ValueError, TypeError):
            logger.warning("Product cache read failed", exc_info=True)
            return None, None

    def set(self, page: int, page_size: int, payload: dict[str, Any], version: str | None) -> None:
        if version is None:
            return
        key = f"products:list:v{version}:p{page}:s{page_size}"
        try:
            self.client.setex(key, 60, json.dumps(payload))
        except RedisError:
            logger.warning("Product cache write failed", exc_info=True)

    def invalidate(self) -> None:
        try:
            self.client.incr(VERSION_KEY)
        except RedisError:
            logger.warning("Product cache invalidation failed", exc_info=True)
