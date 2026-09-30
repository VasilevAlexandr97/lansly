from datetime import UTC, datetime

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lansly.analytics.consts import MULTIPLE_CATEGORIES_MIN
from lansly.analytics.dto import (
    CategoryFollowCounts,
    DailyNewUserCount,
    DailyNotificationCount,
    TopFollowedCategory,
)
from lansly.analytics.interfaces import OverviewGateway
from lansly.notifications.models import ProjectNotification
from lansly.preferences.models import UserCategoryFollow
from lansly.projects.models import Project, ProjectCategory
from lansly.subscriptions.models import Subscription
from lansly.users.models import User


class SAOverviewGateway(OverviewGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_users(self) -> int:
        stmt = select(func.count(User.id))
        result = await self.session.scalar(stmt)
        return result or 0

    async def count_new_users(
        self,
        start_at: datetime,
        end_at: datetime,
        source: str | None = None,
    ) -> int:
        stmt = select(func.count(User.id)).where(
            User.created_at >= start_at,
            User.created_at < end_at,
        )
        if source is not None:
            stmt = stmt.where(User.source == source)
        result = await self.session.scalar(stmt)
        return result or 0

    async def get_new_user_counts_by_day(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[DailyNewUserCount]:
        day = User.created_at.op("AT TIME ZONE")("UTC").cast(Date)

        stmt = (
            select(day, func.count(User.id))
            .where(
                User.created_at >= start_at,
                User.created_at < end_at,
            )
            .group_by(day)
            .order_by(day.asc())
        )

        rows = (await self.session.execute(stmt)).all()
        return [
            DailyNewUserCount(day=row_day, count=count)
            for row_day, count in rows
        ]

    async def count_notifications(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        stmt = select(func.count(ProjectNotification.sent_at)).where(
            ProjectNotification.sent_at >= start_at,
            ProjectNotification.sent_at < end_at,
        )
        result = await self.session.scalar(stmt)
        return result or 0

    async def count_notification_recipients(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        stmt = select(
            func.count(ProjectNotification.user_id.distinct()),
        ).where(
            ProjectNotification.sent_at >= start_at,
            ProjectNotification.sent_at < end_at,
        )
        result = await self.session.scalar(stmt)
        return result or 0

    async def get_notification_counts_by_day(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[DailyNotificationCount]:
        day = ProjectNotification.sent_at.op("AT TIME ZONE")("UTC").cast(Date)
        stmt = (
            select(day, func.count())
            .where(
                ProjectNotification.sent_at >= start_at,
                ProjectNotification.sent_at < end_at,
            )
            .group_by(day)
            .order_by(day.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            DailyNotificationCount(day=row_day, count=count)
            for row_day, count in rows
        ]

    async def get_active_category_follow_counts(
        self,
    ) -> CategoryFollowCounts:
        categories_per_user = (
            select(
                UserCategoryFollow.user_id,
                func.count(UserCategoryFollow.category_id).label(
                    "category_count",
                ),
            )
            .join(User, User.id == UserCategoryFollow.user_id)
            .where(
                UserCategoryFollow.is_active.is_(True),
                User.telegram_id.is_not(None),
            )
            .group_by(UserCategoryFollow.user_id)
            .subquery()
        )

        stmt = select(
            func.count().filter(categories_per_user.c.category_count == 1),
            func.count().filter(
                categories_per_user.c.category_count
                >= MULTIPLE_CATEGORIES_MIN,
            ),
        ).select_from(categories_per_user)

        one, two_or_more = (await self.session.execute(stmt)).one()
        return CategoryFollowCounts(
            one_category=one,
            two_or_more_categories=two_or_more,
        )

    async def get_top_followed_categories(
        self,
        limit: int,
    ) -> list[TopFollowedCategory]:
        followers_count = func.count(
            UserCategoryFollow.user_id.distinct(),
        ).label("followers_count")
        stmt = (
            select(
                ProjectCategory.id,
                ProjectCategory.title,
                ProjectCategory.source,
                followers_count,
            )
            .join(
                UserCategoryFollow,
                UserCategoryFollow.category_id == ProjectCategory.id,
            )
            .join(User, User.id == UserCategoryFollow.user_id)
            .where(
                UserCategoryFollow.is_active.is_(True),
                User.telegram_id.is_not(None),
            )
            .group_by(
                ProjectCategory.id,
                ProjectCategory.title,
                ProjectCategory.source,
            )
            .order_by(
                followers_count.desc(),
                ProjectCategory.source.asc(),
                ProjectCategory.title.asc(),
                ProjectCategory.id.asc(),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            TopFollowedCategory(
                category_id=category_id,
                title=title,
                source=source,
                followers_count=count,
            )
            for category_id, title, source, count in rows
        ]

    async def count_active_subscription_users(self) -> int:
        stmt = select(
            func.count(Subscription.user_id.distinct()),
        ).where(
            Subscription.expires_at > datetime.now(UTC),
        )
        return await self.session.scalar(stmt) or 0

    async def count_projects(
        self,
        start_at: datetime,
        end_at: datetime,
        source: str | None = None,
    ) -> int:
        stmt = select(func.count(Project.id)).where(
            Project.created_at >= start_at,
            Project.created_at < end_at,
        )
        if source is not None:
            stmt = stmt.where(Project.source == source)
        result = await self.session.scalar(stmt)
        return result or 0
