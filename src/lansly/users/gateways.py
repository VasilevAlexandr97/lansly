import logging

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lansly.users.exceptions import (
    CreateUserError,
    UserAlreadyExistsError,
    UserRoleCreationError,
    UserRoleNotFoundError,
)
from lansly.users.interfaces import UserGateway, UserRoleGateway
from lansly.users.models import Role, User, UserRole

logger = logging.getLogger(__name__)


class SAUserGateway(UserGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, new_user: User) -> None:
        try:
            self.session.add(new_user)
            await self.session.flush()
        except IntegrityError as exc:
            if "unique constraint" in str(exc.orig).lower():
                raise UserAlreadyExistsError
            raise CreateUserError

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        return await self.session.scalar(stmt)

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return await self.session.scalar(stmt)

    async def get_user_id_by_telegram_id(
        self,
        telegram_id: int,
    ) -> UUID | None:
        stmt = select(User.id).where(User.telegram_id == telegram_id)
        return await self.session.scalar(stmt)

    async def get_telegram_id_by_user_id(self, user_id: UUID) -> int | None:
        stmt = select(User.telegram_id).where(User.id == user_id)
        return await self.session.scalar(stmt)

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return await self.session.scalar(stmt)

    async def exists(self, user_id: UUID) -> bool:
        stmt = select(exists().where(User.id == user_id))
        result = await self.session.scalar(stmt)
        return bool(result)

    async def get_username(self, user_id: UUID) -> str | None:
        stmt = select(User.username).where(User.id == user_id)
        return await self.session.scalar(stmt)


class SAUserRoleGateway(UserRoleGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, new_role: UserRole) -> None:
        try:
            self.session.add(new_role)
            await self.session.flush()
        except IntegrityError:
            logger.exception(f"User role: {new_role} creation error")
            raise UserRoleCreationError(new_role)

    async def get_role_by_telegram_id(self, telegram_id: int) -> Role:
        stmt = (
            select(UserRole.name)
            .join_from(User, UserRole)
            .where(User.telegram_id == telegram_id)
        )
        result = await self.session.scalar(stmt)
        if not result:
            raise UserRoleNotFoundError
        return Role(result)

    async def get_role_by_user_id(self, user_id: UUID) -> Role:
        stmt = (
            select(UserRole.name)
            .join_from(User, UserRole)
            .where(User.id == user_id)
        )
        result = await self.session.scalar(stmt)
        if not result:
            raise UserRoleNotFoundError
        return Role(result)
