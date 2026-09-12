from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from lansly.common.interfaces.lock_manager import DistributedLockManager


class RedisDistributedLockManager(DistributedLockManager):
    def __init__(self, redis: Redis):
        self.redis = redis

    @asynccontextmanager
    async def try_lock(
        self,
        key: str,
        *,
        timeout: float | None,
        blocking: bool = False,
        blocking_timeout: float | None = None,
    ) -> AsyncIterator[bool]:
        lock = self.redis.lock(
            name=key,
            timeout=timeout,
            blocking=blocking,
            blocking_timeout=blocking_timeout,
        )
        acquired = await lock.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                await lock.release()
