from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class ProjectProposalGenerationRequestStatus(StrEnum):
    CREATED = "created"
    ALREADY_PENDING = "already_pending"
    ALREADY_GENERATED = "already_generated"


@dataclass(frozen=True)
class ProjectProposalGenerationRequestResult:
    status: ProjectProposalGenerationRequestStatus
    generated_text: str | None = None


@dataclass
class MarketPlaceCategory:
    id: str
    title: str
    subcategories: tuple[Self, ...] = ()


@dataclass
class MarketPlaceProject:
    id: str
    category_id: str | None
    price: int
    possible_price_limit: int
    title: str
    description: str
    offers: int
    customer: "MarketPlaceCustomer | None"


@dataclass
class MarketPlaceCustomer:
    id: str
    username: str | None = None
    profile_picture: str | None = None
    user_projects_count: int | None = None
    user_hired_percent: int | None = None
