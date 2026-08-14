from datetime import date as dt_type

from lansly.statistics.dto import MetricRow


class FakeDailyMetricsGateway:
    def __init__(self):
        self.upserted: list[list[MetricRow]] = []
        self.deleted_days: list[dt_type] = []
        self.cleared = 0
        self.operations: list[str] = []

    async def upsert(self, rows: list[MetricRow]) -> None:
        self.operations.append("upsert")
        self.upserted.append(rows)

    async def clear_all(self) -> None:
        self.cleared += 1
        self.operations.append("clear_all")

    async def delete_for_day(self, day: dt_type) -> None:
        self.operations.append("delete")
        self.deleted_days.append(day)


class FakeProjectDailyStatsGateway:
    def __init__(
        self,
        earliest_date: dt_type | None = None,
        compute_day_rows: list[MetricRow] | None = None,
    ):
        self.earliest_date = earliest_date
        self.compute_day_rows = compute_day_rows or []
        self.earliest_calls = 0
        self.compute_day_calls: list[dt_type] = []

    async def get_earliest_project_date(self) -> dt_type | None:
        self.earliest_calls += 1
        return self.earliest_date

    async def compute_day(self, day: dt_type) -> list[MetricRow]:
        self.compute_day_calls.append(day)
        return self.compute_day_rows
