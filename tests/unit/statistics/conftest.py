import pytest

from fakes.infra import FakeTransactionManager
from fakes.statistics import (
    FakeDailyMetricsGateway,
    FakeNotificationDailyStatsGateway,
    FakeProjectDailyStatsGateway,
)

from lansly.statistics.services import DailyMetricsService


@pytest.fixture
def project_stats_gateway() -> FakeProjectDailyStatsGateway:
    return FakeProjectDailyStatsGateway()


@pytest.fixture
def daily_metrics_gateway() -> FakeDailyMetricsGateway:
    return FakeDailyMetricsGateway()


@pytest.fixture
def notification_stats_gateway() -> FakeNotificationDailyStatsGateway:
    return FakeNotificationDailyStatsGateway()


@pytest.fixture
def service(
    project_stats_gateway: FakeProjectDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    notification_stats_gateway: FakeNotificationDailyStatsGateway,
    txn: FakeTransactionManager,
) -> DailyMetricsService:
    return DailyMetricsService(
        daily_metrics_gateway=daily_metrics_gateway,
        project_daily_stats_gateway=project_stats_gateway,
        notification_daily_stats_gateway=notification_stats_gateway,
        transaction_manager=txn,
    )
