from datetime import (
    UTC,
    date as dt_type,
    datetime,
)

import pytest

from sqlalchemy.dialects import postgresql

from lansly.statistics.consts import (
    ALL_DIMENSION,
    DailyMetricName,
    category_dimension,
    source_dimension,
)
from lansly.statistics.gateways import SAProjectDailyStatsGateway

DIALECT = postgresql.dialect()


class _FakeSession:
    pass


@pytest.fixture
def gateway() -> SAProjectDailyStatsGateway:
    return SAProjectDailyStatsGateway(session=_FakeSession())


BUCKET_BOUNDS = [
    (DailyMetricName.PROJECTS_BUCKET_LT_1K, [1000]),
    (DailyMetricName.PROJECTS_BUCKET_FROM_1K_TO_5K, [1000, 5000]),
    (DailyMetricName.PROJECTS_BUCKET_FROM_5K_TO_15K, [5000, 15000]),
    (DailyMetricName.PROJECTS_BUCKET_FROM_15K_TO_30K, [15000, 30000]),
    (DailyMetricName.PROJECTS_BUCKET_GT_30K, [30000]),
]


@pytest.mark.parametrize(("metric", "bounds"), BUCKET_BOUNDS)
def test_bucket_metric_filters_on_price_bounds(
    gateway: SAProjectDailyStatsGateway,
    metric: DailyMetricName,
    bounds: list[int],
):
    compiled = gateway._metric_expression(metric).compile(dialect=DIALECT)
    assert "FILTER (WHERE" in compiled.string
    assert sorted(compiled.params.values()) == sorted(bounds)


def test_count_metric_is_plain_count(gateway: SAProjectDailyStatsGateway):
    compiled = gateway._metric_expression(
        DailyMetricName.PROJECTS_COUNT,
    ).compile(dialect=DIALECT)
    assert compiled.string == "count(*)"


def test_sum_price_metric_coalesces_zero(gateway: SAProjectDailyStatsGateway):
    compiled = gateway._metric_expression(
        DailyMetricName.PROJECTS_SUM_PRICE,
    ).compile(dialect=DIALECT)
    assert "coalesce(sum(projects.price)," in compiled.string
    assert 0 in compiled.params.values()


def test_min_max_metrics_aggregate_price(gateway: SAProjectDailyStatsGateway):
    assert (
        "min(projects.price)"
        in gateway._metric_expression(DailyMetricName.PROJECTS_MIN_PRICE)
        .compile(dialect=DIALECT)
        .string
    )
    assert (
        "max(projects.price)"
        in gateway._metric_expression(DailyMetricName.PROJECTS_MAX_PRICE)
        .compile(dialect=DIALECT)
        .string
    )


def test_unknown_metric_raises_value_error(
    gateway: SAProjectDailyStatsGateway,
):
    with pytest.raises(ValueError):
        gateway._metric_expression("projects.unknown")


def test_all_metrics_have_supported_expressions(
    gateway: SAProjectDailyStatsGateway,
):
    assert len(SAProjectDailyStatsGateway._ALL_METRICS) == 9
    for metric in SAProjectDailyStatsGateway._ALL_METRICS:
        gateway._metric_expression(metric)


def test_rows_from_values_builds_rows_in_metric_order(
    gateway: SAProjectDailyStatsGateway,
):
    day = dt_type(2026, 8, 10)
    metrics = SAProjectDailyStatsGateway._ALL_METRICS
    values = [10, 200_000, 500, 60_000, 2, 3, 4, 5, 6]

    rows = gateway._rows_from_values(day, ALL_DIMENSION, metrics, values)

    assert [row.metric for row in rows] == list(metrics)
    assert [row.value for row in rows] == values
    assert all(row.date == day for row in rows)
    assert all(row.dimension == ALL_DIMENSION for row in rows)


def test_rows_from_values_skips_none_for_nullable_metrics(
    gateway: SAProjectDailyStatsGateway,
):
    metrics = SAProjectDailyStatsGateway._ALL_METRICS
    values = [10, 200_000, None, None, 2, 3, 4, 5, 6]

    rows = gateway._rows_from_values(
        dt_type(2026, 8, 10),
        ALL_DIMENSION,
        metrics,
        values,
    )

    assert len(rows) == 7
    assert DailyMetricName.PROJECTS_MIN_PRICE not in [
        row.metric for row in rows
    ]
    assert DailyMetricName.PROJECTS_MAX_PRICE not in [
        row.metric for row in rows
    ]


def test_rows_from_values_without_metrics_returns_empty(
    gateway: SAProjectDailyStatsGateway,
):
    assert (
        gateway._rows_from_values(dt_type(2026, 8, 10), ALL_DIMENSION, (), ())
        == []
    )


def test_day_range_uses_utc_day_bounds(gateway: SAProjectDailyStatsGateway):
    start, end = gateway._day_range(dt_type(2026, 8, 10))
    assert start == datetime(2026, 8, 10, tzinfo=UTC)
    assert end == datetime(2026, 8, 11, tzinfo=UTC)


def test_source_dimension_formats_source_prefix():
    assert source_dimension("kwork") == "source:kwork"


def test_category_dimension_formats_source_and_external_id():
    assert category_dimension("kwork", "23") == "cat:kwork:23"


def test_category_dimension_uses_uncategorized_when_no_external_id():
    assert category_dimension("kwork", None) == "cat:kwork:none"
