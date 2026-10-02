from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from lansly.notifications.interfaces import (
    ChannelNotificationGateway,
    ProjectNotificationGateway,
)
from lansly.notifications.models import (
    ChannelNotification,
    ProjectNotification,
)


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
