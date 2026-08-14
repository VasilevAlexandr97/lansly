import logging

from datetime import datetime
from uuid import UUID

from dishka.integrations.taskiq import FromDishka, inject

from lansly.infra.taskiq.broker import broker
from lansly.notifications.services import (
    ProjectNotificationService,
    ProjectProposalNotificationService,
    SubscriptionNotificationService,
)
from lansly.projects.services import (
    ProjectProposalGenerationService,
    ProjectSyncService,
)
from lansly.statistics.services import DailyMetricsService
from lansly.subscriptions.services import (
    PaymentVerificationService,
    SubscriptionRenewalService,
)

logger = logging.getLogger(__name__)


@broker.task(schedule=[{"cron": "* * * * *"}])
@inject
async def monitoring_new_projects(
    service: FromDishka[ProjectSyncService],
):
    new_projects = await service.get_and_save_new_projects()
    logger.info(f"NEW PROJECTS: {new_projects}")
    if new_projects:
        await notify_new_projects.kiq(new_projects)
        await notify_new_projects_to_channel.kiq(new_projects)


@broker.task()
@inject
async def notify_new_projects(
    new_projects: list[UUID],
    service: FromDishka[ProjectNotificationService],
):
    await service.notify_new_projects(new_projects)


@broker.task()
@inject
async def notify_new_projects_to_channel(
    new_projects: list[UUID],
    service: FromDishka[ProjectNotificationService],
):
    await service.notify_new_projects_to_channel(
        project_ids=new_projects,
    )


@broker.task()
@inject
async def generate_project_proposal_task(
    user_id: UUID,
    project_id: UUID,
    service: FromDishka[ProjectProposalGenerationService],
):
    await service.generate_proposal_for_user(
        user_id=user_id,
        project_id=project_id,
    )


@broker.task()
@inject
async def notify_project_proposal_generated_task(
    user_id: UUID,
    project_id: UUID,
    service: FromDishka[ProjectProposalNotificationService],
):
    await service.notify_generated(user_id=user_id, project_id=project_id)


@broker.task()
@inject
async def notify_project_proposal_generated_failed_task(
    user_id: UUID,
    service: FromDishka[ProjectProposalNotificationService],
):
    await service.notify_generated_failed(user_id=user_id)


@broker.task(schedule=[{"cron": "* * * * *"}])
@inject
async def verify_pending_payments(
    service: FromDishka[PaymentVerificationService],
):
    await service.verify_pending_payments()


@broker.task()
@inject
async def notify_subscription_activated(
    user_id: UUID,
    service: FromDishka[SubscriptionNotificationService],
):
    await service.notify_activated(user_id)


@broker.task(schedule=[{"cron": "* */4 * * *"}])
@inject
async def auto_renew_subscriptions(
    service: FromDishka[SubscriptionRenewalService],
):
    await service.renew_subscriptions()


@broker.task()
@inject
async def notify_subscription_renewed(
    user_id: UUID,
    new_expires_at: datetime,
    service: FromDishka[SubscriptionNotificationService],
):
    await service.notify_renewed(user_id, new_expires_at)


@broker.task()
@inject
async def notify_subscription_retry(
    user_id: UUID,
    service: FromDishka[SubscriptionNotificationService],
):
    await service.notify_retry(user_id)


@broker.task()
@inject
async def notify_subscription_revoked(
    user_id: UUID,
    service: FromDishka[SubscriptionNotificationService],
):
    await service.notify_revoked(user_id)


@broker.task(schedule=[{"cron": "1 0 * * *"}])
@inject
async def collect_daily_metrics(service: FromDishka[DailyMetricsService]):
    logger.info("Collect daily metrics")
    await service.compute_yesterday()
