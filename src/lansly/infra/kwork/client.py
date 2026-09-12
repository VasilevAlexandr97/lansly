import logging

from kwork import Kwork

from lansly.projects.consts import Marketplace
from lansly.projects.dto import (
    MarketplaceCategory,
    MarketplaceCustomer,
    MarketplaceProject,
)
from lansly.projects.interfaces import MarketplaceClient

logger = logging.getLogger(__name__)


class KworkClient(MarketplaceClient):
    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self.client = Kwork(
            login=self.login,
            password=self.password,
            retry_max_attempts=3,
            timeout=30,
        )

    async def get_categories(self) -> list[MarketplaceCategory]:
        async with self.client as api:
            categories = await api.get_categories()
        if not categories:
            return []
        result = []
        for category in categories:
            if category.id is None:
                logger.info(f"Skip kwork category: {category}")
                continue
            marketplace_category = MarketplaceCategory(
                id=str(category.id),
                source=Marketplace.KWORK,
                title=category.name or "",
            )
            subcategories = []
            for subcategory in category.subcategories or []:
                if subcategory.id is None:
                    logger.info(f"Skip kwork subcategory: {subcategory}")
                    continue
                subcategories.append(
                    MarketplaceCategory(
                        id=str(subcategory.id),
                        source=Marketplace.KWORK,
                        title=subcategory.name or "",
                    ),
                )
            if subcategories:
                marketplace_category.subcategories = tuple(subcategories)
            result.append(marketplace_category)
        return result

    async def get_projects(self, page: int = 1) -> list[MarketplaceProject]:
        async with self.client as api:
            projects = await api.get_projects(
                categories_ids=["all"],
                page=page,
            )
        if not projects:
            return []
        result = []
        for project in projects:
            if project.id is None:
                logger.info(f"Skip kwork project without id: {project}")
                continue
            customer = None
            customer_user_id = project.user_id
            customer_username = project.username
            customer_profile_picture = project.profile_picture
            customer_projects_count = project.user_projects_count
            customer_hired_percent = project.user_hired_percent
            if customer_user_id is not None and customer_username is not None:
                customer = MarketplaceCustomer(
                    id=str(project.user_id),
                    username=customer_username,
                    profile_picture=(
                        customer_profile_picture
                        if customer_profile_picture
                        and "noprofilepicture.gif"
                        not in customer_profile_picture
                        else None
                    ),
                    user_projects_count=(
                        customer_projects_count
                        if customer_projects_count is not None
                        else 0
                    ),
                    user_hired_percent=(
                        customer_hired_percent
                        if customer_hired_percent is not None
                        else 0
                    ),
                )
            result.append(
                MarketplaceProject(
                    id=str(project.id),
                    category_id=(
                        str(project.category_id)
                        if project.category_id is not None
                        else None
                    ),
                    source=Marketplace.KWORK,
                    price=project.price if project.price is not None else 0,
                    possible_price_limit=(
                        project.possible_price_limit
                        if project.possible_price_limit is not None
                        else 0
                    ),
                    has_exact_budget=True,
                    title=project.title or "",
                    description=project.description or "",
                    offers=project.offers if project.offers is not None else 0,
                    customer=customer,
                ),
            )
        return result

    async def get_project(self, project_id: str) -> MarketplaceProject | None:
        return
