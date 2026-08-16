from dataclasses import dataclass
from datetime import date as dt_type

import orjson

from lansly.statistics.consts import DailyMetricName


@dataclass(frozen=True)
class MetricRow:
    date: dt_type
    metric: DailyMetricName
    dimension: str
    value: int


@dataclass(frozen=True)
class WeekPeriod:
    start: dt_type
    end: dt_type
    is_complete: bool


@dataclass(frozen=True)
class MetricComparison:
    current: int
    previous: int
    delta: int
    delta_pct: float | None


@dataclass(frozen=True)
class CategoryInfo:
    title: str
    parent_title: str | None


@dataclass(frozen=True)
class CategoryStats:
    source: str
    external_id: str
    title: str
    parent_title: str | None
    metrics: dict[str, MetricComparison]


@dataclass(frozen=True)
class Coverage:
    days_with_data: int
    total_days: int
    missing_dates: list[dt_type]


@dataclass(frozen=True)
class WeeklyReport:
    ref_date: dt_type
    current_week: WeekPeriod
    previous_week: WeekPeriod
    overall: dict[str, MetricComparison]
    buckets: dict[str, MetricComparison]
    by_category: list[CategoryStats]
    top: dict[str, list[CategoryStats]]
    coverage: Coverage

    def to_json(self) -> str:
        return orjson.dumps(
            {
                "ref_date": self.ref_date,
                "weeks": {
                    "current": self.current_week,
                    "previous": self.previous_week,
                },
                "overall": self.overall,
                "buckets": self.buckets,
                "by_category": self.by_category,
                "top": self.top,
                "coverage": self.coverage,
            },
            option=orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE,
        ).decode("utf-8")
