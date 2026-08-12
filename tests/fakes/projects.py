from lansly.projects.dto import MarketPlaceCategory, MarketPlaceProject
from lansly.projects.models import Project, ProjectCategory


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

    async def bulk_insert(self, projects: list[Project]) -> None:
        self.bulk_insert_calls += 1
        self.bulk_inserted.extend(projects)

    async def get_missing_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> set[str]:
        return set(external_ids) - self.existing_external_ids


class FakeMarketPlaceClient:
    def __init__(
        self,
        categories: list[MarketPlaceCategory] | None = None,
        projects: list[MarketPlaceProject] | None = None,
    ):
        self.categories = categories or []
        self.projects = projects or []
        self.get_categories_calls = 0
        self.get_projects_calls: list[dict] = []

    async def get_categories(self) -> list[MarketPlaceCategory]:
        self.get_categories_calls += 1
        return self.categories

    async def get_projects(
        self,
        categories_ids: list[int | str],
        page: int = 1,
    ) -> list[MarketPlaceProject]:
        self.get_projects_calls.append(
            {"categories_ids": categories_ids, "page": page},
        )
        return self.projects
