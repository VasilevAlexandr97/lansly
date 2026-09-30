import logging

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid7

from lansly.auth.exceptions import AuthenticationError
from lansly.auth.interfaces import IdProvider
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.users.exceptions import (
    CreateUserError,
    SourceLengthError,
    UserAlreadyExistsError,
)
from lansly.users.interfaces import UserGateway, UserRoleGateway
from lansly.users.models import Role, User, UserRole
from lansly.users.validators import source_validator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramAuthResultDTO:
    user_id: UUID
    is_new: bool
    is_pro: bool
    is_admin: bool


class TelegramAuth:
    def __init__(
        self,
        user_gateway: UserGateway,
        user_role_gateway: UserRoleGateway,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.user_gateway = user_gateway
        self.user_role_gateway = user_role_gateway
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def auth(self, source: str | None = None) -> TelegramAuthResultDTO:
        try:
            user = await self.id_provider.get_current_user()
            return TelegramAuthResultDTO(
                user_id=user.id,
                is_new=False,
                is_pro=user.is_pro,
                is_admin=user.is_admin,
            )
        except AuthenticationError:
            pass
        telegram_id = await self.id_provider.get_current_user_telegram_id()
        now = datetime.now(tz=UTC)
        try:
            source_validator(source)
        except SourceLengthError as exc:
            logger.warning(exc)
            source = None
        new_user = User(
            id=uuid7(),
            telegram_id=telegram_id,
            source=source,
            created_at=now,
            updated_at=now,
        )
        new_user_role = UserRole(
            id=uuid7(),
            name=Role.USER,
            user_id=new_user.id,
            created_at=now,
            updated_at=now,
        )
        try:
            await self.user_gateway.add(new_user)
            await self.user_role_gateway.add(new_user_role)
            await self.transaction_manager.commit()
        except UserAlreadyExistsError:
            await self.transaction_manager.rollback()
            logger.info(f"User already exists: {new_user!r}")
            user = await self.id_provider.get_current_user()
            return TelegramAuthResultDTO(
                user_id=user.id,
                is_new=False,
                is_pro=user.is_pro,
                is_admin=user.is_admin,
            )
        except CreateUserError:
            await self.transaction_manager.rollback()
            logger.info(f"User not created: {new_user!r}")
            raise
        return TelegramAuthResultDTO(
            user_id=new_user.id,
            is_new=True,
            is_pro=False,
            is_admin=False,
        )
