from datetime import datetime
from uuid import UUID

from lansly.background_tasks.notification_tasks import (
    notify_project_users,
)
from lansly.background_tasks.tasks import (
    generate_project_proposal_task,
    notify_project_proposal_generated_failed_task,
    notify_project_proposal_generated_task,
    notify_subscription_activated,
    notify_subscription_renewed,
    notify_subscription_retry,
    notify_subscription_revoked,
)
from lansly.notifications.interfaces import (
    ProjectNotificationQueue,
    ProposalGeneratedNotificationQueue,
    SubscriptionActivatedNotificationQueue,
    SubscriptionRenewalNotificationQueue,
)
from lansly.projects.interfaces import (
    ProposalGenerationQueue,
)


class TaskiqProjectNotificationQueue(ProjectNotificationQueue):
    async def enqueue(self, project_ids: list[UUID]) -> None:
        if not project_ids:
            return

        await notify_project_users.kiq(project_ids=project_ids)


class TaskiqProposalGenerationQueue(ProposalGenerationQueue):
    async def enqueue(self, user_id: UUID, project_id: UUID) -> None:
        await generate_project_proposal_task.kiq(
            user_id=user_id,
            project_id=project_id,
        )


class TaskiqProposalGeneratedNotificationQueue(
    ProposalGeneratedNotificationQueue,
):
    async def enqueue_succeeded(self, user_id: UUID, project_id: UUID) -> None:
        await notify_project_proposal_generated_task.kiq(
            user_id=user_id,
            project_id=project_id,
        )

    async def enqueue_failed(self, user_id: UUID) -> None:
        await notify_project_proposal_generated_failed_task.kiq(user_id)


class TaskiqSubscriptionActivatedNotificationQueue(
    SubscriptionActivatedNotificationQueue,
):
    async def enqueue(self, user_id: UUID) -> None:
        await notify_subscription_activated.kiq(user_id=user_id)


class TaskiqSubscriptionRenewalNotificationQueue(
    SubscriptionRenewalNotificationQueue,
):
    async def enqueue_renewed(
        self,
        user_id: UUID,
        new_expires_at: datetime,
    ) -> None:
        await notify_subscription_renewed.kiq(
            user_id=user_id,
            new_expires_at=new_expires_at,
        )

    async def enqueue_retry(self, user_id: UUID) -> None:
        await notify_subscription_retry.kiq(user_id=user_id)

    async def enqueue_revoked(self, user_id: UUID) -> None:
        await notify_subscription_revoked.kiq(user_id=user_id)
