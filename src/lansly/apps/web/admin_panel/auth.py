import logging

from dishka import AsyncContainer
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed

from lansly.auth.exceptions import (
    AlreadyAuthenticatedError,
    AuthenticationError,
)
from lansly.auth.interfaces import IdProvider
from lansly.auth.log_in import LogIn
from lansly.auth.log_out import LogOut
from lansly.users.exceptions import (
    InvalidPasswordError,
    InvalidUsernameError,
    PasswordLengthError,
    UsernameLengthError,
    UserNotFoundByUsernameError,
)
from lansly.users.models import Role

logger = logging.getLogger(__name__)


class AdminPanelAuthProvider(AuthProvider):
    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
    ):
        # Получение контейнера через state
        container: AsyncContainer = request.scope["state"]["dishka_container"]
        async with container() as r_c:
            log_in = await r_c.get(LogIn)
            try:
                await log_in.authenticate(
                    username=username,
                    password=password,
                    required_role=Role.ADMIN,
                )
                return
            except AuthenticationError:
                logger.info(f"User {username} auth error")
            except AlreadyAuthenticatedError:
                logger.info(f"User {username} already authenticated")
                return
            except UserNotFoundByUsernameError:
                logger.info(f"User {username} not found")
                raise LoginFailed("Authenticated Error")
            except (
                UsernameLengthError,
                InvalidUsernameError,
                PasswordLengthError,
                InvalidPasswordError,
            ):
                logger.info(f"Invalid username {username} or password")
        raise LoginFailed("Invalid username or password")

    async def authenticate(self, request: Request) -> AdminUser | None:
        container: AsyncContainer = request.scope["state"]["dishka_container"]
        async with container() as r_c:
            id_provider = await r_c.get(IdProvider)
            try:
                user = await id_provider.get_current_user()
                if user.is_admin:
                    return AdminUser(
                        username=f"{user.username}",
                    )
            except AuthenticationError:
                return None
        return None

    async def logout(self, request: Request):
        container: AsyncContainer = request.scope["state"]["dishka_container"]
        async with container() as r_c:
            auth = await r_c.get(LogOut)
            await auth.invalidate()
