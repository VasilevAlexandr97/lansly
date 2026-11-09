from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from lansly.notifications.interfaces import (
    ChannelNotificationGateway,
    ProjectNotificationGateway,
)
from lansly.notifications.models import (
    ChannelNotification,
    ProjectNotification,
)
from lansly.preferences.models import UserCategoryFollow
from lansly.subscriptions.consts import TRIAL_DAYS
from lansly.subscriptions.models import Subscription
from lansly.users.models import Role, User, UserRole


class SAProjectNotificationGateway(ProjectNotificationGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_upsert(
        self,
        notifications: list[ProjectNotification],
    ) -> None:
        if not notifications:
            return

        values = [
            {
                "project_id": notification.project_id,
                "user_id": notification.user_id,
                "project_updated_at": notification.project_updated_at,
                "sent_at": notification.sent_at,
                "error": notification.error,
            }
            for notification in notifications
        ]

        stmt = pg_insert(ProjectNotification).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_id", "user_id"],
            set_={
                "project_updated_at": stmt.excluded.project_updated_at,
                "sent_at": stmt.excluded.sent_at,
                "error": stmt.excluded.error,
            },
        )
        await self.session.execute(stmt)

    async def get(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> ProjectNotification | None:
        stmt = select(ProjectNotification).where(
            ProjectNotification.project_id == project_id,
            ProjectNotification.user_id == user_id,
        )
        return await self.session.scalar(stmt)

    async def get_recipients_for_category(
        self,
        category_id: UUID,
    ) -> list[User]:
        now = datetime.now(UTC)
        trial_cutoff = now - timedelta(days=TRIAL_DAYS)
        active_trial = and_(
            User.trial_started_at > trial_cutoff,
            User.trial_started_at <= now,
        )
        is_admin = (
            select(UserRole.id)
            .where(UserRole.user_id == User.id, UserRole.name == Role.ADMIN)
            .exists()
        )
        active_subscription = (
            select(Subscription.id)
            .where(
                Subscription.user_id == User.id,
                Subscription.expires_at > now,
            )
            .exists()
        )
        stmt = (
            select(User)
            .join(UserCategoryFollow, UserCategoryFollow.user_id == User.id)
            .where(
                UserCategoryFollow.category_id == category_id,
                UserCategoryFollow.is_active.is_(True),
                User.telegram_id.is_not(None),
                User.is_telegram_unavailable.is_(False),
                or_(active_trial, is_admin, active_subscription),
            )
        )
        result = await self.session.scalars(stmt)
        return list(result.all())


# TODO: удалить функционал связанный с чатом
class SAChannelNotificationGateway(ChannelNotificationGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_insert(
        self,
        notifications: list[ChannelNotification],
    ) -> None:
        if not notifications:
            return
        values = [
            {
                "project_id": notification.project_id,
                "sent_at": notification.sent_at,
            }
            for notification in notifications
        ]
        stmt = insert(ChannelNotification).values(values)
        await self.session.execute(stmt)
