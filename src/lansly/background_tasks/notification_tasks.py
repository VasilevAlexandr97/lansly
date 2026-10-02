from uuid import UUID

from dishka.integrations.taskiq import FromDishka, inject

from lansly.infra.taskiq.broker import notification_broker
from lansly.notifications.services import ProjectNotificationService


@notification_broker.task(
    task_name="notifications:projects:users",
    retry_on_error=True,
)
@inject(patch_module=True)
async def notify_project_users(
    project_ids: list[UUID],
    service: FromDishka[ProjectNotificationService],
) -> None:
    await service.notify_new_projects(project_ids)


@notification_broker.task(task_name="notifications:projects:channel")
@inject(patch_module=True)
async def notify_project_channel(
    project_ids: list[UUID],
    service: FromDishka[ProjectNotificationService],
) -> None:
    await service.notify_new_projects_to_channel(project_ids=project_ids)
