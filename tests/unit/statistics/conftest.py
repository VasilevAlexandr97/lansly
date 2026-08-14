import pytest

from fakes.infra import FakeTransactionManager
from fakes.statistics import (
    FakeDailyMetricsGateway,
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
def service(
    project_stats_gateway: FakeProjectDailyStatsGateway,
    daily_metrics_gateway: FakeDailyMetricsGateway,
    txn: FakeTransactionManager,
) -> DailyMetricsService:
    return DailyMetricsService(
        daily_metrics_gateway=daily_metrics_gateway,
        project_daily_stats_gateway=project_stats_gateway,
        transaction_manager=txn,
    )
