import datetime

from dataclasses import dataclass

from lansly.statistics.consts import DailyMetricName


@dataclass(frozen=True)
class MetricRow:
    date: datetime.date
    metric: DailyMetricName
    dimension: str
    value: int
