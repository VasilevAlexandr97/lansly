from lansly.auth.exceptions import ForbiddenError
from lansly.users.models import Role


def require_admin(role: Role) -> None:
    if role != Role.ADMIN:
        raise ForbiddenError("Admin access required")
