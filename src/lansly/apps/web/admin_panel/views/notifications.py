from starlette_admin.contrib.sqla import ModelView

from lansly.notifications.models import ProjectNotification


class ProjectNotificationView(ModelView):
    fields = [  # noqa: RUF012
        ProjectNotification.project_id,
        ProjectNotification.user_id,
        ProjectNotification.sent_at,
    ]
    fields_default_sort = [(ProjectNotification.sent_at, True)]  # noqa: RUF012
