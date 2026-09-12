from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Protocol


class DistributedLockManager(Protocol):
    @abstractmethod
    def try_lock(
        self,
        key: str,
        *,
        timeout: float | None,
        blocking: bool = False,
        blocking_timeout: float | None = None,
    ) -> AbstractAsyncContextManager[bool]:
        raise NotImplementedError
