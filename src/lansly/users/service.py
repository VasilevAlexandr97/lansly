import logging

from datetime import UTC, datetime
from uuid import uuid7

from lansly.common.interfaces.password_hasher import PasswordHasher
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.users.dto import AdminUserDTO
from lansly.users.exceptions import CreateUserError, UserAlreadyExistsError
from lansly.users.interfaces import UserGateway, UserRoleGateway
from lansly.users.models import Role, User, UserRole
from lansly.users.validators import password_validator, username_validator

logger = logging.getLogger(__name__)


class CreateAdminUserService:
    def __init__(
        self,
        user_gateway: UserGateway,
        user_role_gateway: UserRoleGateway,
        transaction_manager: TransactionManager,
        password_hasher: PasswordHasher,
    ):
        self.user_gateway = user_gateway
        self.user_role_gateway = user_role_gateway
        self.transaction_manager = transaction_manager
        self.password_hasher = password_hasher

    async def create(self, username: str, password: str) -> AdminUserDTO:
        username_validator(username)
        password_validator(password)
        user = await self.user_gateway.get_by_username(username)
        if user:
            raise UserAlreadyExistsError
        password_hash = self.password_hasher.hash(password)
        now = datetime.now(UTC)
        new_user = User(
            id=uuid7(),
            username=username,
            password_hash=password_hash,
            created_at=now,
            updated_at=now,
            trial_started_at=now,
        )
        new_user_role = UserRole(
            id=uuid7(),
            name=Role.ADMIN,
            user_id=new_user.id,
            created_at=now,
            updated_at=now,
        )
        try:
            await self.user_gateway.add(new_user)
            await self.user_role_gateway.add(new_user_role)
            await self.transaction_manager.commit()
        except (UserAlreadyExistsError, CreateUserError):
            await self.transaction_manager.rollback()
            logger.info(f"User not created: {new_user!r}")
            raise
        return AdminUserDTO(
            user_id=new_user.id,
            username=username,
        )
