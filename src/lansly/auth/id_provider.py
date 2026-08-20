import logging

from uuid import UUID

from fastapi import Request

from lansly.auth.exceptions import AuthenticationError
from lansly.auth.interfaces import (
    IdProvider,
    SessionManager,
)
from lansly.auth.session import AuthSession
from lansly.common.dto import CurrentUser
from lansly.subscriptions.interfaces import SubscriptionChecker
from lansly.users.interfaces import UserGateway, UserRoleGateway
from lansly.users.models import Role

logger = logging.getLogger(__name__)


class TelegramIdProvider(IdProvider):
    def __init__(
        self,
        telegram_id: int,
        user_gateway: UserGateway,
        user_role_gateway: UserRoleGateway,
        sub_checker: SubscriptionChecker,
    ):
        self.telegram_id = telegram_id
        self.user_gateway = user_gateway
        self.user_role_gateway = user_role_gateway
        self.sub_checker = sub_checker
        # TODO: Закэшировать пользователя

        self.cached_user_id: UUID | None = None
        self.cached_role: Role | None = None

    async def get_current_user_telegram_id(self) -> int | None:
        return self.telegram_id

    async def _get_user_id(self) -> UUID:
        if self.cached_user_id is not None:
            logger.debug(f"CACHED USER ID: {self.cached_user_id}")
            return self.cached_user_id
        user_id = await self.user_gateway.get_user_id_by_telegram_id(
            self.telegram_id,
        )
        if not user_id:
            raise AuthenticationError(
                f"User with telegram_id: {self.telegram_id} not found",
            )
        logger.debug(f"USER ID: {user_id}")
        self.cached_user_id = user_id
        return user_id

    async def _get_user_role(self) -> Role:
        if self.cached_role is not None:
            logger.debug(f"CACHED USER ROLE: {self.cached_role}")
            return self.cached_role
        role = await self.user_role_gateway.get_role_by_telegram_id(
            telegram_id=self.telegram_id,
        )
        logger.debug(f"USER ROLE: {role}")
        self.cached_role = role
        return role

    async def get_current_user_id(self) -> UUID:
        # TODO: Получать сразу user_id, а не всего юзера
        return await self._get_user_id()

    async def get_role(self) -> Role:
        return await self._get_user_role()

    async def get_current_user(self) -> CurrentUser:
        user_id = await self._get_user_id()
        is_pro = await self.sub_checker.is_pro_subscription(user_id)
        role = await self._get_user_role()
        return CurrentUser(
            id=user_id,
            is_pro=is_pro,
            is_admin=role == Role.ADMIN,
        )


class SessionIdProvider(IdProvider):
    def __init__(
        self,
        request: Request,
        user_gateway: UserGateway,
        user_role_gateway: UserRoleGateway,
        sub_checker: SubscriptionChecker,
        session_manager: SessionManager,
    ):
        self.request = request
        self.user_gateway = user_gateway
        self.user_role_gateway = user_role_gateway
        self.sub_checker = sub_checker
        self.session_manager = session_manager

        self._cached_session: AuthSession | None = None
        self._cached_role: Role | None = None

    async def _get_session(self) -> AuthSession:
        if self._cached_session is not None:
            logger.debug(f"CACHED SESSION: {self._cached_session}")
            return self._cached_session
        session = await self.session_manager.get_session()
        if session is None:
            raise AuthenticationError("Auth session not found")
        self._cached_session = session
        return session

    async def _get_role(self, user_id: UUID) -> Role:
        if self._cached_role is not None:
            logger.debug(f"CACHED USER ROLE: {self._cached_role}")
            return self._cached_role
        role = await self.user_role_gateway.get_role_by_user_id(user_id)
        logger.debug(f"USER ROLE: {role}")
        self._cached_role = role
        return role

    async def get_current_user_telegram_id(self) -> int | None:
        session = await self._get_session()
        return await self.user_gateway.get_telegram_id_by_user_id(
            session.user_id,
        )

    async def get_current_user_id(self) -> UUID:
        session = await self._get_session()
        exists = await self.user_gateway.exists(session.user_id)
        if not exists:
            raise AuthenticationError("User not found")
        return session.user_id

    async def get_role(self) -> Role:
        session = await self._get_session()
        return await self._get_role(session.user_id)

    async def get_current_user(self) -> CurrentUser:
        session = await self._get_session()
        username = await self.user_gateway.get_username(session.user_id)
        is_pro = await self.sub_checker.is_pro_subscription(session.user_id)
        role = await self._get_role(session.user_id)
        return CurrentUser(
            id=session.user_id,
            username=username,
            is_pro=is_pro,
            is_admin=role == Role.ADMIN,
        )


class WorkerIdProvider(IdProvider):
    async def get_current_user_telegram_id(self) -> int:
        return 0

    async def get_current_user_id(self) -> UUID:
        return UUID("00000000-0000-0000-0000-000000000000")

    async def get_role(self) -> Role:
        return Role.USER

    async def get_current_user(self) -> CurrentUser:
        raise NotImplementedError


class WebIdProvider(IdProvider):
    async def get_current_user_telegram_id(self) -> int:
        return 0

    async def get_current_user_id(self) -> UUID:
        return UUID("00000000-0000-0000-0000-000000000000")

    async def get_role(self) -> Role:
        return Role.USER

    async def get_current_user(self) -> CurrentUser:
        raise NotImplementedError
