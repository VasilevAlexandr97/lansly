from starlette.requests import Request
from starlette_admin.contrib.sqla import ModelView

from lansly.notifications.models import ProjectNotification


class ProjectNotificationView(ModelView):
    fields = [  # noqa: RUF012
        ProjectNotification.project_id,
        ProjectNotification.user_id,
        ProjectNotification.sent_at,
        ProjectNotification.error,
        ProjectNotification.project_updated_at,
    ]
    fields_default_sort = [(ProjectNotification.sent_at, True)]  # noqa: RUF012

    def can_create(self, request: Request) -> bool:  # noqa: ARG002
        return False

    def can_edit(self, request: Request) -> bool:  # noqa: ARG002
        return False

    def can_delete(self, request: Request) -> bool:  # noqa: ARG002
        return False
