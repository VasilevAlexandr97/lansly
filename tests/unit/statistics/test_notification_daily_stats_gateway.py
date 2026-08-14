from datetime import (
    UTC,
    date as dt_type,
    datetime,
)

import pytest

from sqlalchemy.dialects import postgresql

from lansly.statistics.consts import ALL_DIMENSION, DailyMetricName
from lansly.statistics.dto import MetricRow
from lansly.statistics.gateways import SANotificationDailyStatsGateway

DIALECT = postgresql.dialect()
DAY = dt_type(2026, 8, 10)
DAY_START = datetime(2026, 8, 10, tzinfo=UTC)
DAY_END = datetime(2026, 8, 11, tzinfo=UTC)


class _RecordingSession:
    def __init__(self, results):
        self.results = list(results)
        self.statements: list = []
        self._i = 0

    async def scalar(self, stmt):
        self.statements.append(stmt)
        value = self.results[self._i]
        self._i += 1
        return value


def compile_string(stmt) -> str:
    return stmt.compile(dialect=DIALECT).string


def test_day_range_uses_utc_day_bounds():
    start, end = SANotificationDailyStatsGateway._day_range(DAY)
    assert start == DAY_START
    assert end == DAY_END


@pytest.mark.asyncio
async def test_compute_day_runs_two_single_table_queries_no_cross_join():
    gateway = SANotificationDailyStatsGateway(
        session=_RecordingSession(results=[5, 3]),
    )

    rows = await gateway.compute_day(DAY)

    assert len(gateway.session.statements) == 2
    pn_sql = compile_string(gateway.session.statements[0])
    cn_sql = compile_string(gateway.session.statements[1])
    assert "FROM project_notifications" in pn_sql
    assert "channel_notifications" not in pn_sql
    assert "FROM channel_notifications" in cn_sql
    assert "project_notifications" not in cn_sql
    assert rows == [
        MetricRow(DAY, DailyMetricName.NOTIFICATIONS_COUNT, ALL_DIMENSION, 5),
        MetricRow(
            DAY, DailyMetricName.CHANNEL_NOTIFICATIONS_COUNT, ALL_DIMENSION, 3,
        ),
    ]


@pytest.mark.asyncio
async def test_earliest_queries_each_table_separately():
    gateway = SANotificationDailyStatsGateway(
        session=_RecordingSession(results=[dt_type(2026, 8, 5), None]),
    )

    result = await gateway.get_earliest_notification_date()

    assert len(gateway.session.statements) == 2
    pn_sql = compile_string(gateway.session.statements[0])
    cn_sql = compile_string(gateway.session.statements[1])
    assert (
        "project_notifications" in pn_sql
        and "channel_notifications" not in pn_sql
    )
    assert (
        "channel_notifications" in cn_sql
        and "project_notifications" not in cn_sql
    )
    assert "min(" in pn_sql and "AT TIME ZONE" in pn_sql
    assert result == dt_type(2026, 8, 5)


@pytest.mark.asyncio
async def test_earliest_returns_none_when_both_tables_empty():
    gateway = SANotificationDailyStatsGateway(
        session=_RecordingSession(results=[None, None]),
    )
    assert await gateway.get_earliest_notification_date() is None


@pytest.mark.asyncio
async def test_earliest_uses_min_when_one_table_empty():
    gateway = SANotificationDailyStatsGateway(
        session=_RecordingSession(results=[None, dt_type(2026, 8, 3)]),
    )
    assert await gateway.get_earliest_notification_date() == dt_type(
        2026,
        8,
        3,
    )
