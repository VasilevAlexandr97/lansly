from datetime import (
    UTC,
    date as dt_type,
    datetime,
)

import pytest

from fakes.infra import FakeTransactionManager
from fakes.statistics import (
    FakeDailyMetricsGateway,
    FakeNotificationDailyStatsGateway,
    FakeProjectDailyStatsGateway,
)

from lansly.statistics.consts import ALL_DIMENSION, DailyMetricName
from lansly.statistics.dto import MetricRow
from lansly.statistics.services import DailyMetricsService

DAY = dt_type(2026, 8, 10)
NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)


def make_row(
    day: dt_type = DAY,
    metric: DailyMetricName = DailyMetricName.PROJECTS_COUNT,
    dimension: str = ALL_DIMENSION,
    value: int = 1,
) -> MetricRow:
    return MetricRow(day, metric, dimension, value)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.replace(tzinfo=tz)


@pytest.mark.asyncio
async def test_compute_for_day_combines_project_and_notification_rows(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
):
    project_rows = [
        make_row(),
        make_row(metric=DailyMetricName.PROJECTS_SUM_PRICE),
    ]
    notification_rows = [
        make_row(metric=DailyMetricName.NOTIFICATIONS_COUNT),
        make_row(metric=DailyMetricName.CHANNEL_NOTIFICATIONS_COUNT),
    ]
    project_stats_gateway.compute_day_rows = project_rows
    notification_stats_gateway.compute_day_rows = notification_rows

    await service.compute_for_day(DAY)

    assert project_stats_gateway.compute_day_calls == [DAY]
    assert notification_stats_gateway.compute_day_calls == [DAY]
    assert daily_metrics_gateway.operations == ["delete", "upsert"]
    assert daily_metrics_gateway.deleted_days == [DAY]
    assert daily_metrics_gateway.upserted == [project_rows + notification_rows]
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_compute_for_day_deletes_even_without_rows(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
):
    await service.compute_for_day(DAY)

    assert project_stats_gateway.compute_day_calls == [DAY]
    assert notification_stats_gateway.compute_day_calls == [DAY]
    assert daily_metrics_gateway.operations == ["delete", "upsert"]
    assert daily_metrics_gateway.deleted_days == [DAY]
    assert daily_metrics_gateway.upserted == [[]]
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_compute_yesterday_uses_previous_utc_day(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
    monkeypatch,
):
    monkeypatch.setattr("lansly.statistics.services.datetime", FrozenDatetime)

    await service.compute_yesterday()

    expected = dt_type(2026, 8, 14)
    assert project_stats_gateway.compute_day_calls == [expected]
    assert notification_stats_gateway.compute_day_calls == [expected]
    assert daily_metrics_gateway.deleted_days == [expected]
    assert daily_metrics_gateway.upserted == [[]]
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_recompute_all_noop_without_data(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
):
    project_stats_gateway.earliest_date = None
    notification_stats_gateway.earliest_notification_date = None

    await service.recompute_all()

    assert project_stats_gateway.earliest_calls == 1
    assert notification_stats_gateway.earliest_calls == 1
    assert project_stats_gateway.compute_day_calls == []
    assert notification_stats_gateway.compute_day_calls == []
    assert daily_metrics_gateway.cleared == 0
    assert daily_metrics_gateway.upserted == []
    assert daily_metrics_gateway.deleted_days == []
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_recompute_all_noop_when_earliest_is_after_end(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
    monkeypatch,
):
    monkeypatch.setattr("lansly.statistics.services.datetime", FrozenDatetime)
    project_stats_gateway.earliest_date = dt_type(2026, 8, 15)
    notification_stats_gateway.earliest_notification_date = None

    await service.recompute_all()

    assert project_stats_gateway.compute_day_calls == []
    assert notification_stats_gateway.compute_day_calls == []
    assert daily_metrics_gateway.cleared == 0
    assert daily_metrics_gateway.upserted == []
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_recompute_all_computes_each_day_and_commits_once(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
    monkeypatch,
):
    monkeypatch.setattr("lansly.statistics.services.datetime", FrozenDatetime)
    project_stats_gateway.earliest_date = dt_type(2026, 8, 10)
    notification_stats_gateway.earliest_notification_date = None

    await service.recompute_all()

    expected = [
        dt_type(2026, 8, 10),
        dt_type(2026, 8, 11),
        dt_type(2026, 8, 12),
        dt_type(2026, 8, 13),
        dt_type(2026, 8, 14),
    ]
    assert project_stats_gateway.compute_day_calls == expected
    assert notification_stats_gateway.compute_day_calls == expected
    assert daily_metrics_gateway.cleared == 1
    assert len(daily_metrics_gateway.upserted) == 5
    assert daily_metrics_gateway.deleted_days == []
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_recompute_all_uses_notification_earliest_when_project_is_none(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
    monkeypatch,
):
    monkeypatch.setattr("lansly.statistics.services.datetime", FrozenDatetime)
    project_stats_gateway.earliest_date = None
    notification_stats_gateway.earliest_notification_date = dt_type(
        2026, 8, 10,
    )

    await service.recompute_all()

    expected = [
        dt_type(2026, 8, 10),
        dt_type(2026, 8, 11),
        dt_type(2026, 8, 12),
        dt_type(2026, 8, 13),
        dt_type(2026, 8, 14),
    ]
    assert project_stats_gateway.compute_day_calls == expected
    assert notification_stats_gateway.compute_day_calls == expected
    assert daily_metrics_gateway.cleared == 1
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_recompute_all_uses_min_of_project_and_notification_earliest(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
    monkeypatch,
):
    monkeypatch.setattr("lansly.statistics.services.datetime", FrozenDatetime)
    project_stats_gateway.earliest_date = dt_type(2026, 8, 12)
    notification_stats_gateway.earliest_notification_date = dt_type(
        2026, 8, 10,
    )

    await service.recompute_all()

    expected = [
        dt_type(2026, 8, 10),
        dt_type(2026, 8, 11),
        dt_type(2026, 8, 12),
        dt_type(2026, 8, 13),
        dt_type(2026, 8, 14),
    ]
    assert project_stats_gateway.compute_day_calls == expected
    assert notification_stats_gateway.compute_day_calls == expected
    assert daily_metrics_gateway.cleared == 1
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_recompute_all_combines_project_and_notification_rows(
    service: DailyMetricsService,
    project_stats_gateway: FakeProjectDailyStatsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
    monkeypatch,
):
    monkeypatch.setattr("lansly.statistics.services.datetime", FrozenDatetime)
    project_stats_gateway.earliest_date = dt_type(2026, 8, 10)
    project_stats_gateway.compute_day_rows = [
        make_row(metric=DailyMetricName.PROJECTS_COUNT),
    ]
    notification_stats_gateway.compute_day_rows = [
        make_row(metric=DailyMetricName.NOTIFICATIONS_COUNT),
    ]

    await service.recompute_all()

    expected = (
        project_stats_gateway.compute_day_rows
        + notification_stats_gateway.compute_day_rows
    )
    assert len(daily_metrics_gateway.upserted) == 5
    assert daily_metrics_gateway.upserted == [expected] * 5
    assert txn.commits == 1
