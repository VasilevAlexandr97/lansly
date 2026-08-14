from abc import abstractmethod
from datetime import date as dt_type
from typing import Protocol

from lansly.statistics.dto import MetricRow


class DailyMetricsGateway(Protocol):
    @abstractmethod
    async def upsert(self, rows: list[MetricRow]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear_all(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_for_day(self, day: dt_type) -> None:
        raise NotImplementedError


class ProjectDailyStatsGateway(Protocol):
    @abstractmethod
    async def get_earliest_project_date(self) -> dt_type | None:
        raise NotImplementedError

    @abstractmethod
    async def compute_day(self, day: dt_type) -> list[MetricRow]:
        raise NotImplementedError


class NotificationDailyStatsGateway(Protocol):
    @abstractmethod
    async def get_earliest_notification_date(self) -> dt_type | None:
        raise NotImplementedError

    @abstractmethod
    async def compute_day(self, day: dt_type) -> list[MetricRow]:
        raise NotImplementedError
