from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyNewUserCount:
    day: date
    count: int


@dataclass(frozen=True)
class DailyNotificationCount:
    day: date
    count: int


@dataclass(frozen=True)
class CategoryFollowCounts:
    one_category: int
    two_or_more_categories: int
