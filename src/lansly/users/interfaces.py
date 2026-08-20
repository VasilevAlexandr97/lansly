from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from lansly.users.models import Role, User, UserRole


class UserGateway(Protocol):
    @abstractmethod
    async def add(self, new_user: User) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def get_user_id_by_telegram_id(
        self,
        telegram_id: int,
    ) -> UUID | None:
        raise NotImplementedError

    @abstractmethod
    async def get_telegram_id_by_user_id(self, user_id: UUID) -> int | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_username(self, user_id: UUID) -> str | None:
        raise NotImplementedError


class UserRoleGateway(Protocol):
    @abstractmethod
    async def add(self, new_role: UserRole) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_role_by_telegram_id(self, telegram_id: int) -> Role:
        raise NotImplementedError

    @abstractmethod
    async def get_role_by_user_id(self, user_id: UUID) -> Role:
        raise NotImplementedError
