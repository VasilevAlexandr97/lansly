from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from lansly.projects.dto import MarketPlaceCategory, MarketPlaceProject
from lansly.projects.models import (
    Customer,
    Project,
    ProjectCategory,
    UserGenerationUsage,
)


class ProjectCategoryGateway(Protocol):
    @abstractmethod
    async def upsert(self, categories: list[ProjectCategory]):
        raise NotImplementedError

    @abstractmethod
    async def get_categories_by_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> list[ProjectCategory]:
        raise NotImplementedError

    @abstractmethod
    async def get_root_categories(
        self,
        source: str | None = None,
    ) -> list[ProjectCategory]:
        raise NotImplementedError


class ProjectGateway(Protocol):
    @abstractmethod
    async def bulk_insert(self, projects: list[Project]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_missing_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    async def get_projects_by_ids(
        self,
        project_ids: list[UUID],
        with_category: bool = False,
        with_customer: bool = False,
    ) -> list[Project]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, project_id: UUID) -> Project | None:
        raise NotImplementedError


class CustomerGateway(Protocol):
    @abstractmethod
    async def bulk_upsert(self, customers: list[Customer]) -> list[Customer]:
        raise NotImplementedError


class MarketPlaceClient(Protocol):
    @abstractmethod
    async def get_categories(self) -> list[MarketPlaceCategory]:
        raise NotImplementedError

    @abstractmethod
    async def get_projects(
        self,
        categories_ids: list[int | str],
        page: int = 1,
    ) -> list[MarketPlaceProject]:
        raise NotImplementedError


class ProposalGenerationQueue(Protocol):
    @abstractmethod
    async def enqueue(self, user_id: UUID, project_id: UUID) -> None:
        raise NotImplementedError


class GenerationLimitChecker(Protocol):
    @abstractmethod
    async def can_generate(self, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_limit(self, user_id: UUID) -> int:
        raise NotImplementedError


class UserGenerationUsageGateway:
    @abstractmethod
    async def get_or_create(self, user_id: UUID) -> UserGenerationUsage:
        raise NotImplementedError
