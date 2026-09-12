from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from lansly.projects.consts import Marketplace


class ProjectProposalGenerationRequestStatus(StrEnum):
    CREATED = "created"
    ALREADY_PENDING = "already_pending"
    ALREADY_GENERATED = "already_generated"


@dataclass(frozen=True)
class ProjectProposalGenerationRequestResult:
    status: ProjectProposalGenerationRequestStatus
    generated_text: str | None = None


@dataclass
class MarketplaceCategory:
    id: str
    source: Marketplace
    title: str
    subcategories: tuple[Self, ...] = ()


@dataclass
class MarketplaceProject:
    id: str
    category_id: str | None
    source: Marketplace
    price: int
    possible_price_limit: int
    has_exact_budget: bool
    title: str
    description: str
    offers: int
    customer: "MarketplaceCustomer | None"


@dataclass
class MarketplaceCustomer:
    id: str
    username: str
    profile_picture: str | None = None
    user_projects_count: int = 0
    user_hired_percent: int = 0


@dataclass(frozen=True)
class ProjectLinks:
    project_url: str
    customer_url: str | None = None
