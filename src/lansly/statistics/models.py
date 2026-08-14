import datetime

from sqlalchemy import BigInteger, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from lansly.infra.database.base import Base
from lansly.statistics.consts import (
    DIMENSION_MAX_LENGTH,
    METRIC_NAME_MAX_LENGTH,
)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(
        String(METRIC_NAME_MAX_LENGTH),
        primary_key=True,
    )
    dimension: Mapped[str] = mapped_column(
        String(DIMENSION_MAX_LENGTH),
        primary_key=True,
    )
    value: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"DailyMetric(date={self.date}, metric={self.metric}, "
            f"dimension={self.dimension}, value={self.value})"
        )
