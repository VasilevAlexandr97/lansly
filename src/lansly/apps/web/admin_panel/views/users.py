from starlette.requests import Request
from starlette_admin.contrib.sqla import ModelView

from lansly.users.models import User, UserRole


class UserView(ModelView):
    fields = [  # noqa: RUF012
        User.id,
        User.telegram_id,
        User.source,
        User.created_at,
        User.updated_at,
        User.is_telegram_unavailable,
    ]

    fields_default_sort = [(User.created_at, True)]  # noqa: RUF012


class UserRoleView(ModelView):
    fields = [  # noqa: RUF012
        UserRole.id,
        UserRole.name,
        UserRole.user_id,
        UserRole.created_at,
        UserRole.updated_at,
    ]

    def can_create(self, request: Request) -> bool:  # noqa: ARG002
        return False

    def can_edit(self, request: Request) -> bool:  # noqa: ARG002
        return False

    def can_delete(self, request: Request) -> bool:  # noqa: ARG002
        return False
