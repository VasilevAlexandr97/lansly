from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from lansly.analytics.dto import (
    CategoryFollowCounts,
    DailyNewUserCount,
    DailyNotificationCount,
)


class OverviewGateway(Protocol):
    @abstractmethod
    async def count_users(self) -> int:
        raise NotImplementedError

    @abstractmethod
    async def count_new_users(
        self,
        start_at: datetime,
        end_at: datetime,
        source: str | None = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_new_user_counts_by_day(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[DailyNewUserCount]:
        raise NotImplementedError

    @abstractmethod
    async def count_notifications(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def count_notification_recipients(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_notification_counts_by_day(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[DailyNotificationCount]:
        raise NotImplementedError

    @abstractmethod
    async def get_active_category_follow_counts(
        self,
    ) -> CategoryFollowCounts:
        raise NotImplementedError

    @abstractmethod
    async def count_active_subscription_users(self) -> int:
        raise NotImplementedError

    @abstractmethod
    async def count_projects(
        self,
        start_at: datetime,
        end_at: datetime,
        source: str | None = None,
    ) -> int:
        raise NotImplementedError
