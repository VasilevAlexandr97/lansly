from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass


class FakeTransactionManager:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        self.rollbacks += 1


@dataclass(frozen=True, slots=True)
class LockCall:
    key: str
    timeout: float | None
    blocking: bool
    blocking_timeout: float | None


class FakeDistributedLockManager:
    def __init__(self, acquired: bool = True):
        self.acquired = acquired
        self.calls: list[LockCall] = []
        self.enter_count = 0
        self.exit_count = 0

    @asynccontextmanager
    async def try_lock(
        self,
        key: str,
        *,
        timeout: float | None,
        blocking: bool = False,
        blocking_timeout: float | None = None,
    ) -> AsyncIterator[bool]:
        self.calls.append(
            LockCall(
                key=key,
                timeout=timeout,
                blocking=blocking,
                blocking_timeout=blocking_timeout,
            ),
        )
        self.enter_count += 1

        try:
            yield self.acquired
        finally:
            self.exit_count += 1
