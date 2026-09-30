from starlette_admin.contrib.sqla import ModelView

from lansly.users.models import User


class UserView(ModelView):
    fields = [  # noqa: RUF012
        User.id,
        User.telegram_id,
        User.source,
        User.created_at,
        User.updated_at,
    ]

    fields_default_sort = [(User.created_at, True)]  # noqa: RUF012
