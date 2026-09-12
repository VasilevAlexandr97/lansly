from dataclasses import dataclass
from uuid import UUID

from lansly.projects.consts import Marketplace
from lansly.projects.models import ProjectCategory


@dataclass(frozen=True)
class DirectionWithFollowCountsDTO:
    id: UUID
    title: str
    followed_count: int
    total_count: int


@dataclass(frozen=True)
class CategoryWithFollowedStatusDTO:
    category: ProjectCategory
    is_followed: bool


@dataclass(frozen=True)
class SubcategoriesWithFollowStatusDTO:
    categories: list[CategoryWithFollowedStatusDTO]
    limit: int


@dataclass(frozen=True)
class SourceCategoryFollowCountDTO:
    source: Marketplace
    followed_count: int


@dataclass
class FollowCategoryDTO:
    category_id: UUID
    title: str


@dataclass(frozen=True)
class StopWordsDTO:
    words: list[str]
    available: int
    limit: int


@dataclass(frozen=True)
class CountStopWordsDTO:
    count: int
    available: int
    limit: int
