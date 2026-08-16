import logging

from collections import defaultdict
from datetime import (
    UTC,
    date as dt_type,
    datetime,
    timedelta,
)

from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.statistics.consts import (
    ALL_DIMENSION,
    UNCATEGORIZED,
    UNCATEGORIZED_LABEL,
    DailyMetricName,
    category_dimension,
    parse_category_dimension,
)
from lansly.statistics.dto import (
    CategoryInfo,
    CategoryStats,
    Coverage,
    MetricComparison,
    MetricRow,
    WeeklyReport,
    WeekPeriod,
)
from lansly.statistics.interfaces import (
    DailyMetricsGateway,
    NotificationDailyStatsGateway,
    ProjectDailyStatsGateway,
    WeeklyStatsGateway,
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


class WeeklyReportService:
    def __init__(self, gateway: WeeklyStatsGateway):
        self.gateway = gateway

    def _last_completed_weeks(
        self,
        ref_date: dt_type,
    ) -> tuple[WeekPeriod, WeekPeriod]:
        current_monday = ref_date - timedelta(days=ref_date.weekday())
        current = WeekPeriod(
            start=current_monday - timedelta(days=7),
            end=current_monday - timedelta(days=1),
            is_complete=True,
        )
        previous = WeekPeriod(
            start=current_monday - timedelta(days=14),
            end=current_monday - timedelta(days=8),
            is_complete=True,
        )
        return current, previous

    def _percent_change(self, current: int, previous: int) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 2)

    async def build(self, top_n: int = 10) -> WeeklyReport:
        current_date = datetime.now(UTC).date()
        current_week, previous_week = self._last_completed_weeks(current_date)
        rows = await self.gateway.get_metrics(
            previous_week.start,
            current_week.end,
        )
        categories = await self.gateway.get_categories()

        current = self._aggregate(rows, current_week)
        previous = self._aggregate(rows, previous_week)

        coverage = self._coverage(rows, current_week)
        current_week = WeekPeriod(
            start=current_week.start,
            end=current_week.end,
            is_complete=coverage.days_with_data == coverage.total_days,
        )
        overall = self._overall(current, previous)
        buckets = self._compare_buckets(current, previous)
        by_category = self._by_category(
            current,
            previous,
            rows,
            categories,
        )
        top = self._top(by_category, top_n)
        return WeeklyReport(
            ref_date=current_date,
            current_week=current_week,
            previous_week=previous_week,
            overall=overall,
            buckets=buckets,
            by_category=by_category,
            top=top,
            coverage=coverage,
        )

    def _aggregate(
        self,
        rows: list[MetricRow],
        week: WeekPeriod,
    ) -> dict[tuple[DailyMetricName, str], int]:
        totals = defaultdict(int)
        for row in rows:
            key = (row.metric, row.dimension)
            if week.start <= row.date <= week.end:
                if row.metric == DailyMetricName.PROJECTS_MIN_PRICE:
                    totals[key] = min(totals.get(key, row.value), row.value)
                elif row.metric == DailyMetricName.PROJECTS_MAX_PRICE:
                    totals[key] = max(totals.get(key, row.value), row.value)
                else:
                    totals[key] += row.value
        return totals

    def _compare(
        self,
        current: dict[tuple[DailyMetricName, str], int],
        previous: dict[tuple[DailyMetricName, str], int],
        metric: DailyMetricName,
        dimension: str = ALL_DIMENSION,
    ) -> MetricComparison | None:
        cur_value = current.get((metric, dimension))
        prev_value = previous.get((metric, dimension))
        if cur_value is None and prev_value is None:
            return None
        cur = cur_value if cur_value is not None else 0
        prev = prev_value if prev_value is not None else 0
        return MetricComparison(
            current=cur,
            previous=prev,
            delta=cur - prev,
            delta_pct=self._percent_change(cur, prev),
        )

    def _compare_avg_price(
        self,
        current: dict[tuple[DailyMetricName, str], int],
        previous: dict[tuple[DailyMetricName, str], int],
        dimension: str = ALL_DIMENSION,
    ) -> MetricComparison | None:
        cur_count = current.get((DailyMetricName.PROJECTS_COUNT, dimension))
        prev_count = previous.get((DailyMetricName.PROJECTS_COUNT, dimension))
        if cur_count is None and prev_count is None:
            return None
        cur_avg = self._avg_price(
            current.get((DailyMetricName.PROJECTS_SUM_PRICE, dimension)),
            cur_count,
        )
        prev_avg = self._avg_price(
            previous.get((DailyMetricName.PROJECTS_SUM_PRICE, dimension)),
            prev_count,
        )
        return MetricComparison(
            current=cur_avg,
            previous=prev_avg,
            delta=cur_avg - prev_avg,
            delta_pct=self._percent_change(cur_avg, prev_avg),
        )

    def _compare_buckets(
        self,
        current: dict[tuple[DailyMetricName, str], int],
        previous: dict[tuple[DailyMetricName, str], int],
    ) -> dict[str, MetricComparison]:
        _metrics = (
            DailyMetricName.PROJECTS_BUCKET_LT_1K,
            DailyMetricName.PROJECTS_BUCKET_FROM_1K_TO_5K,
            DailyMetricName.PROJECTS_BUCKET_FROM_5K_TO_15K,
            DailyMetricName.PROJECTS_BUCKET_FROM_15K_TO_30K,
            DailyMetricName.PROJECTS_BUCKET_GT_30K,
        )
        buckets = {
            metric.value: comparison
            for metric in _metrics
            if (
                comparison := self._compare(
                    current,
                    previous,
                    metric,
                )
            )
            is not None
        }
        return buckets

    def _avg_price(self, total: int | None, count: int | None) -> int:
        if not count:
            return 0
        return round((total or 0) / count)

    def _overall(
        self,
        current: dict[tuple[DailyMetricName, str], int],
        previous: dict[tuple[DailyMetricName, str], int],
    ) -> dict[str, MetricComparison]:
        result = {}
        _metrics = [
            DailyMetricName.PROJECTS_COUNT,
            DailyMetricName.PROJECTS_SUM_PRICE,
            DailyMetricName.PROJECTS_MIN_PRICE,
            DailyMetricName.PROJECTS_MAX_PRICE,
            DailyMetricName.NOTIFICATIONS_COUNT,
            DailyMetricName.CHANNEL_NOTIFICATIONS_COUNT,
        ]
        for metric in _metrics:
            comparison = self._compare(current, previous, metric)
            if comparison is not None:
                result[metric.value] = comparison
        avg_price = self._compare_avg_price(current, previous)
        if avg_price is not None:
            result["projects_avg_price"] = avg_price
        return result

    def _coverage(
        self,
        rows: list[MetricRow],
        week: WeekPeriod,
    ) -> Coverage:
        total_days = (week.end - week.start).days + 1
        days = [
            week.start + timedelta(days=offset) for offset in range(total_days)
        ]
        with_data = {row.date for row in rows} & set(days)
        return Coverage(
            days_with_data=len(with_data),
            total_days=total_days,
            missing_dates=sorted(set(days) - with_data),
        )

    def _by_category(
        self,
        current: dict[tuple[DailyMetricName, str], int],
        previous: dict[tuple[DailyMetricName, str], int],
        rows: list[MetricRow],
        categories: dict[tuple[str, str], CategoryInfo],
    ) -> list[CategoryStats]:
        seen = {
            parsed
            for row in rows
            if (parsed := parse_category_dimension(row.dimension)) is not None
        }
        stats = [
            self._category_stats(
                source,
                external_id,
                current,
                previous,
                categories,
            )
            for source, external_id in seen
        ]
        stats.sort(
            key=lambda item: (
                item.metrics.get(
                    "projects_count",
                    MetricComparison(0, 0, 0, None),
                ).current,
                item.title,
            ),
            reverse=True,
        )
        return stats

    def _category_stats(
        self,
        source: str,
        external_id: str,
        current: dict[tuple[DailyMetricName, str], int],
        previous: dict[tuple[DailyMetricName, str], int],
        categories: dict[tuple[str, str], CategoryInfo],
    ) -> CategoryStats:
        dimension = category_dimension(source, external_id)
        info = categories.get((source, external_id))
        if info is not None:
            title = info.title
            parent_title = info.parent_title
        elif external_id == UNCATEGORIZED:
            title = UNCATEGORIZED_LABEL
            parent_title = None
        else:
            title = f"Категория {external_id}"
            parent_title = None

        metrics: dict[str, MetricComparison] = {}
        for key, metric in (
            ("projects_count", DailyMetricName.PROJECTS_COUNT),
            ("projects_sum_price", DailyMetricName.PROJECTS_SUM_PRICE),
        ):
            comparison = self._compare(
                current,
                previous,
                metric,
                dimension,
            )
            if comparison is not None:
                metrics[key] = comparison
        avg_price = self._compare_avg_price(
            current,
            previous,
            dimension,
        )
        if avg_price is not None:
            metrics["projects_avg_price"] = avg_price

        return CategoryStats(
            source=source,
            external_id=external_id,
            title=title,
            parent_title=parent_title,
            metrics=metrics,
        )

    def _comparison_value(self, stats: CategoryStats, key: str) -> int:
        return stats.metrics.get(key, MetricComparison(0, 0, 0, None)).current

    def _delta_pct_value(self, stats: CategoryStats, key: str) -> float:
        comparison = stats.metrics.get(key)
        if comparison is None or comparison.delta_pct is None:
            return 0.0
        return comparison.delta_pct

    def _top(
        self,
        by_category: list[CategoryStats],
        top_n: int,
    ) -> dict[str, list[CategoryStats]]:
        with_pct = [
            stats
            for stats in by_category
            if stats.metrics.get("projects_count") is not None
            and stats.metrics["projects_count"].delta_pct is not None
        ]
        return {
            "by_projects_count": sorted(
                by_category,
                key=lambda s: self._comparison_value(s, "projects_count"),
                reverse=True,
            )[:top_n],
            "by_sum_price": sorted(
                by_category,
                key=lambda s: self._comparison_value(s, "projects_sum_price"),
                reverse=True,
            )[:top_n],
            "top_growth": sorted(
                with_pct,
                key=lambda s: self._delta_pct_value(s, "projects_count"),
                reverse=True,
            )[:top_n],
            "top_decline": sorted(
                with_pct,
                key=lambda s: self._delta_pct_value(s, "projects_count"),
            )[:top_n],
        }
