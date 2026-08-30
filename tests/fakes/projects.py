from uuid import UUID

from lansly.projects.consts import Marketplace
from lansly.projects.dto import MarketplaceCategory, MarketplaceProject
from lansly.projects.models import Customer, Project, ProjectCategory


class FakeProjectCategoryGateway:
    def __init__(self, existing: list[ProjectCategory] | None = None):
        self.existing = existing or []
        self.upserted: list[ProjectCategory] = []
        self.upsert_calls = 0

    async def upsert(self, categories: list[ProjectCategory]) -> None:
        self.upsert_calls += 1
        self.upserted.extend(categories)

    async def get_categories_by_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> list[ProjectCategory]:
        return [
            category
            for category in self.existing
            if category.external_id in external_ids
            and category.source == source
        ]

    async def get_root_categories(
        self,
        source: str | None = None,
    ) -> list[ProjectCategory]:
        raise NotImplementedError


class FakeProjectGateway:
    def __init__(self, existing_external_ids: set[str] | None = None):
        self.existing_external_ids = existing_external_ids or set()
        self.bulk_inserted: list[Project] = []
        self.bulk_insert_calls = 0

    async def bulk_insert(self, projects: list[Project]) -> list[UUID]:
        self.bulk_insert_calls += 1
        self.bulk_inserted.extend(projects)
        return [project.id for project in projects]

    async def get_missing_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> set[str]:
        return set(external_ids) - self.existing_external_ids


class FakeCustomerGateway:
    def __init__(self):
        self.upserted: list[Customer] = []
        self.upsert_calls = 0

    async def bulk_upsert(self, customers: list[Customer]) -> list[Customer]:
        self.upsert_calls += 1
        self.upserted.extend(customers)
        return customers


class FakeMarketPlaceClient:
    def __init__(
        self,
        categories: list[MarketplaceCategory] | None = None,
        projects: list[MarketplaceProject] | None = None,
    ):
        self.categories = categories or []
        self.projects = projects or []
        self.get_categories_calls = 0
        self.get_projects_calls: list[dict] = []

    async def get_categories(self) -> list[MarketplaceCategory]:
        self.get_categories_calls += 1
        return self.categories

    async def get_projects(
        self,
        categories_ids: list[int | str],
        page: int = 1,
    ) -> list[MarketplaceProject]:
        self.get_projects_calls.append(
            {"categories_ids": categories_ids, "page": page},
        )
        return self.projects


class FakeProjectCollector:
    def __init__(
        self,
        source: Marketplace | None = None,
        projects: list[MarketplaceProject] | None = None,
    ):
        self.source = source or Marketplace.KWORK
        self.projects = projects or []
        self.collect_calls = 0

    async def collect(self) -> list[MarketplaceProject]:
        self.collect_calls += 1
        return self.projects
