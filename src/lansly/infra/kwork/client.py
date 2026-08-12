import logging

from kwork import Kwork

from lansly.projects.dto import MarketPlaceCategory, MarketPlaceProject
from lansly.projects.interfaces import MarketPlaceClient

logger = logging.getLogger(__name__)


class KworkClient(MarketPlaceClient):
    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self.client = Kwork(
            login=self.login,
            password=self.password,
            retry_max_attempts=3,
            timeout=30,
        )

    async def get_categories(self) -> list[MarketPlaceCategory]:
        async with self.client as api:
            categories = await api.get_categories()
        if not categories:
            return []
        result = []
        for category in categories:
            if category.id is None:
                logger.info(f"Skip kwork category: {category}")
                continue
            marketplace_category = MarketPlaceCategory(
                id=str(category.id),
                title=category.name or "",
            )
            subcategories = []
            for subcategory in category.subcategories or []:
                if subcategory.id is None:
                    logger.info(f"Skip kwork subcategory: {subcategory}")
                    continue
                subcategories.append(
                    MarketPlaceCategory(
                        id=str(subcategory.id),
                        title=subcategory.name or "",
                    ),
                )
            if subcategories:
                marketplace_category.subcategories = tuple(subcategories)
            result.append(marketplace_category)
        return result

    async def get_projects(
        self,
        categories_ids: list[int | str],
        page: int = 1,
    ) -> list[MarketPlaceProject]:
        async with self.client as api:
            projects = await api.get_projects(
                categories_ids=categories_ids,
                page=page,
            )
        if not projects:
            return []
        result = []
        for project in projects:
            if project.id is None:
                logger.info(f"Skip kwork project without id: {project}")
                continue
            result.append(
                MarketPlaceProject(
                    id=str(project.id),
                    category_id=(
                        str(project.category_id)
                        if project.category_id is not None
                        else None
                    ),
                    price=project.price if project.price is not None else 0,
                    possible_price_limit=(
                        project.possible_price_limit
                        if project.possible_price_limit is not None
                        else 0
                    ),
                    title=project.title or "",
                    description=project.description or "",
                    offers=project.offers if project.offers is not None else 0,
                ),
            )
        return result
