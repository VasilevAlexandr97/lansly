import logging

from datetime import (
    UTC,
    date as dt_type,
    datetime,
    timedelta,
)

from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.statistics.interfaces import (
    DailyMetricsGateway,
    NotificationDailyStatsGateway,
    ProjectDailyStatsGateway,
)

logger = logging.getLogger(__name__)


class DailyMetricsService:
    def __init__(
        self,
        daily_metrics_gateway: DailyMetricsGateway,
        project_daily_stats_gateway: ProjectDailyStatsGateway,
        notification_daily_stats_gateway: NotificationDailyStatsGateway,
        transaction_manager: TransactionManager,
    ):
        self.daily_metrics_gateway = daily_metrics_gateway
        self.project_daily_stats_gateway = project_daily_stats_gateway
        self.notification_daily_stats_gateway = (
            notification_daily_stats_gateway
        )
        self.transaction_manager = transaction_manager

    async def compute_for_day(self, day: dt_type) -> None:
        project_stats = await self.project_daily_stats_gateway.compute_day(day)
        notification_stats = (
            await self.notification_daily_stats_gateway.compute_day(day)
        )
        rows = project_stats + notification_stats
        await self.daily_metrics_gateway.delete_for_day(day)
        await self.daily_metrics_gateway.upsert(rows)
        await self.transaction_manager.commit()

    async def compute_yesterday(self) -> None:
        logger.info("Collect daily metrics for yesterday")
        yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
        await self.compute_for_day(yesterday)

    async def recompute_all(self) -> None:
        earliest_project = (
            await self.project_daily_stats_gateway.get_earliest_project_date()
        )
        earliest_notification = await self.notification_daily_stats_gateway.get_earliest_notification_date()  # noqa: E501
        dates = [
            d
            for d in (earliest_project, earliest_notification)
            if d is not None
        ]
        if not dates:
            return
        earliest = min(dates)
        end = (datetime.now(UTC) - timedelta(days=1)).date()
        if earliest > end:
            return
        await self.daily_metrics_gateway.clear_all()
        day = earliest
        while day <= end:
            project_stats = await self.project_daily_stats_gateway.compute_day(
                day,
            )
            notification_stats = (
                await self.notification_daily_stats_gateway.compute_day(day)
            )
            rows = project_stats + notification_stats
            await self.daily_metrics_gateway.upsert(rows)
            day += timedelta(days=1)
        await self.transaction_manager.commit()
