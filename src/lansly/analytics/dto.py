from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class DailyNewUserCount:
    day: date
    count: int


@dataclass(frozen=True)
class DailyNotificationCount:
    day: date
    success_count: int
    failed_count: int


@dataclass(frozen=True)
class CategoryFollowCounts:
    one_category: int
    two_or_more_categories: int


@dataclass(frozen=True)
class TopFollowedCategory:
    category_id: UUID
    title: str
    source: str
    followers_count: int
