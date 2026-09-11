from datetime import UTC, datetime
from uuid import uuid7

from lansly.projects.consts import Marketplace
from lansly.projects.dto import MarketplaceProject
from lansly.projects.models import Customer, Project, ProjectCategory


def category(**kwargs):
    return ProjectCategory(
        **(
            {
                "id": uuid7(),
                "external_id": "design",
                "source": Marketplace.FL,
                "title": "Дизайн",
                "parent_id": None,
            }
            | kwargs
        ),
    )


def customer(**kwargs):
    return Customer(
        **(
            {
                "id": uuid7(),
                "external_id": "7",
                "source": Marketplace.KWORK,
                "username": "alice",
                "profile_picture": None,
                "user_projects_count": 12,
                "user_hired_percent": 75,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            | kwargs
        ),
    )


def project(**kwargs):
    cat = kwargs.pop("category", category())
    cust = kwargs.pop("customer", None)
    return Project(
        **(
            {
                "id": uuid7(),
                "external_id": "42",
                "source": Marketplace.FL,
                "category": cat,
                "category_id": cat.id if cat else None,
                "customer": cust,
                "customer_id": cust.id if cust else None,
                "title": "Нарисовать логотип",
                "description": "Нужен дизайн\nС пробелами.",
                "price": 30000,
                "possible_price_limit": 40000,
                "has_exact_budget": True,
                "offers": 3,
                "created_at": datetime.now(UTC),
            }
            | kwargs
        ),
    )


def marketplace_project(**kwargs):
    return MarketplaceProject(
        **(
            {
                "id": "42",
                "category_id": "design",
                "source": Marketplace.FL,
                "title": "Проект",
                "description": "Первый абзац\n\nВторой абзац",
                "price": 30000,
                "possible_price_limit": 30000,
                "has_exact_budget": True,
                "offers": 2,
                "customer": None,
            }
            | kwargs
        ),
    )
