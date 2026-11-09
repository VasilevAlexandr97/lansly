from abc import abstractmethod
from typing import Protocol
from uuid import UUID


class SubscriptionChecker(Protocol):
    @abstractmethod
    async def is_pro_subscription(self, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def is_pro_user(self, user_id: UUID) -> bool:
        raise NotImplementedError


class SubscriptionLimitsResetter(Protocol):
    @abstractmethod
    async def reset_pro_generations(self, user_id: UUID) -> None:
        raise NotImplementedError
