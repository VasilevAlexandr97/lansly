from collections.abc import Sequence
from datetime import (
    UTC,
    date as dt_type,
    datetime,
    timedelta,
)
from typing import Any

from sqlalchemy import ColumnElement, Date, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from lansly.projects.models import Project, ProjectCategory
from lansly.statistics.consts import (
    ALL_DIMENSION,
    UNCATEGORIZED,
    DailyMetricName,
    category_dimension,
    source_dimension,
)
from lansly.statistics.dto import MetricRow
from lansly.statistics.interfaces import (
    DailyMetricsGateway,
    ProjectDailyStatsGateway,
)
from lansly.statistics.models import DailyMetric


class SADailyMetricsGateway(DailyMetricsGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, rows: list[MetricRow]) -> None:
        if not rows:
            return
        values = [
            {
                "date": row.date,
                "metric": row.metric,
                "dimension": row.dimension,
                "value": row.value,
            }
            for row in rows
        ]
        stmt = pg_insert(DailyMetric).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "metric", "dimension"],
            set_={"value": stmt.excluded.value},
        )
        await self.session.execute(stmt)

    async def clear_all(self) -> None:
        await self.session.execute(delete(DailyMetric))

    async def delete_for_day(self, day: dt_type) -> None:
        stmt = delete(DailyMetric).where(DailyMetric.date == day)
        await self.session.execute(stmt)


class SAProjectDailyStatsGateway(ProjectDailyStatsGateway):
    _ALL_METRICS = (
        DailyMetricName.PROJECTS_COUNT,
        DailyMetricName.PROJECTS_SUM_PRICE,
        DailyMetricName.PROJECTS_MIN_PRICE,
        DailyMetricName.PROJECTS_MAX_PRICE,
        DailyMetricName.PROJECTS_BUCKET_LT_1K,
        DailyMetricName.PROJECTS_BUCKET_FROM_1K_TO_5K,
        DailyMetricName.PROJECTS_BUCKET_FROM_5K_TO_15K,
        DailyMetricName.PROJECTS_BUCKET_FROM_15K_TO_30K,
        DailyMetricName.PROJECTS_BUCKET_GT_30K,
    )

    _NULLABLE_METRICS = (
        DailyMetricName.PROJECTS_MIN_PRICE,
        DailyMetricName.PROJECTS_MAX_PRICE,
    )

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _day_range(day: dt_type):
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        return day_start, day_start + timedelta(days=1)

    def _metric_expression(
        self,
        metric: DailyMetricName,
    ) -> ColumnElement[Any]:
        match metric:
            case DailyMetricName.PROJECTS_COUNT:
                return func.count()
            case DailyMetricName.PROJECTS_SUM_PRICE:
                return func.coalesce(func.sum(Project.price), 0)
            case DailyMetricName.PROJECTS_MIN_PRICE:
                return func.min(Project.price)
            case DailyMetricName.PROJECTS_MAX_PRICE:
                return func.max(Project.price)
            case DailyMetricName.PROJECTS_BUCKET_LT_1K:
                return func.count().filter(Project.price < 1000)
            case DailyMetricName.PROJECTS_BUCKET_FROM_1K_TO_5K:
                return func.count().filter(
                    (Project.price >= 1000) & (Project.price < 5000),
                )
            case DailyMetricName.PROJECTS_BUCKET_FROM_5K_TO_15K:
                return func.count().filter(
                    (Project.price >= 5000) & (Project.price < 15000),
                )
            case DailyMetricName.PROJECTS_BUCKET_FROM_15K_TO_30K:
                return func.count().filter(
                    (Project.price >= 15000) & (Project.price < 30000),
                )
            case DailyMetricName.PROJECTS_BUCKET_GT_30K:
                return func.count().filter(Project.price >= 30000)
            case _:
                raise ValueError(f"Unsupported metric: {metric!r}")

    def _rows_from_values(
        self,
        day: dt_type,
        dim: str,
        metrics: tuple[DailyMetricName, ...],
        values: Sequence[Any],
    ) -> list[MetricRow]:
        rows = []
        for metric, value in zip(metrics, values, strict=True):
            if value is None and metric in self._NULLABLE_METRICS:
                continue
            rows.append(MetricRow(day, metric, dim, value))
        return rows

    async def get_earliest_project_date(self) -> dt_type | None:
        stmt = select(
            func.min(Project.created_at.op("AT TIME ZONE")("UTC").cast(Date)),
        )
        return await self.session.scalar(stmt)

    async def compute_day(self, day: dt_type) -> list[MetricRow]:
        rows: list[MetricRow] = []
        rows += await self._compute_all(day)
        rows += await self._compute_by_source(day)
        rows += await self._compute_by_category(day)
        return rows

    async def _compute_all(self, day: dt_type) -> list[MetricRow]:
        day_start, day_end = self._day_range(day)
        aggregates = [self._metric_expression(m) for m in self._ALL_METRICS]
        stmt = select(*aggregates).where(
            Project.created_at >= day_start,
            Project.created_at < day_end,
        )
        values = (await self.session.execute(stmt)).one()
        return self._rows_from_values(
            day,
            ALL_DIMENSION,
            self._ALL_METRICS,
            values,
        )

    async def _compute_by_source(self, day: dt_type) -> list[MetricRow]:
        day_start, day_end = self._day_range(day)
        aggregates = [self._metric_expression(m) for m in self._ALL_METRICS]
        stmt = (
            select(Project.source, *aggregates)
            .where(
                Project.created_at >= day_start,
                Project.created_at < day_end,
            )
            .group_by(Project.source)
        )
        rows = []
        for source, *values in await self.session.execute(stmt):
            rows += self._rows_from_values(
                day,
                source_dimension(source),
                self._ALL_METRICS,
                values,
            )
        return rows

    async def _compute_by_category(self, day: dt_type) -> list[MetricRow]:
        day_start, day_end = self._day_range(day)
        aggregates = [self._metric_expression(m) for m in self._ALL_METRICS]
        src = func.coalesce(ProjectCategory.source, Project.source)
        ext_id = func.coalesce(ProjectCategory.external_id, UNCATEGORIZED)
        stmt = (
            select(src, ext_id, *aggregates)
            .outerjoin(
                ProjectCategory,
                Project.category_id == ProjectCategory.id,
            )
            .where(
                Project.created_at >= day_start,
                Project.created_at < day_end,
            )
            .group_by(src, ext_id)
        )
        rows = []
        for source, ext, *values in await self.session.execute(stmt):
            rows += self._rows_from_values(
                day,
                category_dimension(source, ext),
                self._ALL_METRICS,
                values,
            )
        return rows
