from datetime import UTC, datetime, time, timedelta

from lansly.analytics.dto import (
    CategoryFollowCounts,
    DailyNewUserCount,
    DailyNotificationCount,
)
from lansly.analytics.interfaces import OverviewGateway
from lansly.auth.exceptions import ForbiddenError
from lansly.auth.interfaces import IdProvider
from lansly.users.models import Role


class OverviewService:
    def __init__(self, gateway: OverviewGateway, id_provider: IdProvider):
        self.gateway = gateway
        self.id_provider = id_provider

    def _require_admin(self, user_role: Role) -> None:
        if user_role != Role.ADMIN:
            raise ForbiddenError

    async def count_users(self) -> int:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        return await self.gateway.count_users()

    async def count_new_users(
        self,
        days: int,
        source: str | None = None,
    ) -> int:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        end_at = datetime.now(UTC)
        start_at = end_at - timedelta(days=days)
        return await self.gateway.count_new_users(
            start_at=start_at,
            end_at=end_at,
            source=source,
        )

    async def get_new_user_counts_by_day(
        self,
        days: int,
    ) -> list[DailyNewUserCount]:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)

        end_at = datetime.now(UTC)
        first_day = end_at.date() - timedelta(days=days - 1)
        start_at = datetime.combine(first_day, time.min, tzinfo=UTC)

        rows = await self.gateway.get_new_user_counts_by_day(
            start_at=start_at,
            end_at=end_at,
        )
        counts_by_day = {row.day: row.count for row in rows}

        return [
            DailyNewUserCount(
                day=day,
                count=counts_by_day.get(day, 0),
            )
            for day in (
                first_day + timedelta(days=offset) for offset in range(days)
            )
        ]

    async def count_notifications(self, days: int) -> int:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        end_at = datetime.now(UTC)
        start_at = end_at - timedelta(days=days)
        return await self.gateway.count_notifications(
            start_at=start_at,
            end_at=end_at,
        )

    async def count_notification_recipients(self, days: int) -> int:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        end_at = datetime.now(UTC)
        start_at = end_at - timedelta(days=days)
        return await self.gateway.count_notification_recipients(
            start_at=start_at,
            end_at=end_at,
        )

    async def get_notification_counts_by_day(
        self,
        days: int,
    ) -> list[DailyNotificationCount]:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        end_at = datetime.now(UTC)
        first_day = end_at.date() - timedelta(days=days - 1)
        start_at = datetime.combine(first_day, time.min, tzinfo=UTC)

        rows = await self.gateway.get_notification_counts_by_day(
            start_at=start_at,
            end_at=end_at,
        )
        counts_by_day = {row.day: row.count for row in rows}

        return [
            DailyNotificationCount(
                day=day,
                count=counts_by_day.get(day, 0),
            )
            for day in (
                first_day + timedelta(days=offset) for offset in range(days)
            )
        ]

    async def get_active_category_follow_counts(
        self,
    ) -> CategoryFollowCounts:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        return await self.gateway.get_active_category_follow_counts()

    async def count_active_subscription_users(self) -> int:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        return await self.gateway.count_active_subscription_users()

    async def count_projects(
        self,
        days: int,
        source: str | None = None,
    ) -> int:
        user_role = await self.id_provider.get_role()
        self._require_admin(user_role)
        end_at = datetime.now(UTC)
        start_at = end_at - timedelta(days=days)
        return await self.gateway.count_projects(
            start_at=start_at,
            end_at=end_at,
            source=source,
        )
