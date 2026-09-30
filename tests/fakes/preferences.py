from uuid import UUID

from lansly.preferences.dto import (
    CategoryWithFollowedStatusDTO,
    DirectionWithFollowCountsDTO,
    FollowCategoryDTO,
    SourceCategoryFollowCountDTO,
    SubcategoriesWithFollowStatusDTO,
)
from lansly.projects.consts import Marketplace
from lansly.users.models import User


# TODO: подумать добавить или нет интерфейс для основного сервиса
class FakeFollowService:
    def __init__(
        self,
        follow_counts: list[SourceCategoryFollowCountDTO] | None = None,
    ):
        self.follow_counts = (
            follow_counts
            if follow_counts is not None
            else [
                SourceCategoryFollowCountDTO(source=source, followed_count=0)
                for source in Marketplace
            ]
        )
        self.follow_counts_calls = 0

    async def get_followed_category_counts_by_source(
        self,
    ) -> list[SourceCategoryFollowCountDTO]:
        self.follow_counts_calls += 1
        return self.follow_counts


class MonitoringFollowService(FakeFollowService):
    def __init__(self):
        super().__init__()
        self.directions = {}
        self.categories = {}
        self.followed = set()
        self.calls = []
        self.error = None

    async def get_directions_with_follow_counts(self, source):

        self.calls.append(("directions", source))
        return [
            DirectionWithFollowCountsDTO(
                c.id,
                c.title,
                sum(
                    x.id in self.followed
                    for x in self.categories.get(c.id, [])
                ),
                len(self.categories.get(c.id, [])),
            )
            for c in self.directions.get(source, [])
        ]

    async def get_subcategories_with_follow_status(self, parent_id):

        self.calls.append(("categories", parent_id))
        return [
            CategoryWithFollowedStatusDTO(c, c.id in self.followed)
            for c in self.categories.get(parent_id, [])
        ]

    async def follow_category(self, category_id):

        self.calls.append(("follow", category_id))
        if self.error:
            raise self.error
        category = next(
            c
            for group in self.categories.values()
            for c in group
            if c.id == category_id
        )
        self.followed.add(category_id)
        return FollowCategoryDTO(category.id, category.title)

    async def toggle_category_follow(self, category_id):

        self.calls.append(("toggle", category_id))
        if self.error:
            raise self.error
        self.followed.symmetric_difference_update({category_id})
        parent = next(
            p
            for p, cats in self.categories.items()
            if any(c.id == category_id for c in cats)
        )
        return SubcategoriesWithFollowStatusDTO(
            await self.get_subcategories_with_follow_status(parent),
            1,
        )

    async def unfollow_all_categories(self):
        self.calls.append(("disable",))
        self.followed.clear()


class FakeUserStopWordsGateway:
    def __init__(self) -> None:
        self.words: dict[UUID, list[str]] = {}

    async def get_stop_words_by_user_ids(
        self,
        user_ids: list[UUID],
    ) -> dict[UUID, list[str]]:
        return {
            user_id: self.words[user_id]
            for user_id in user_ids
            if user_id in self.words
        }


class FakeUserPriceFilterGateway:
    def __init__(self) -> None:
        self.prices: dict[UUID, tuple[int, int]] = {}

    async def get_filter_by_user_ids(
        self,
        user_ids: list[UUID],
    ) -> dict[UUID, tuple[int, int]]:
        return {
            user_id: self.prices[user_id]
            for user_id in user_ids
            if user_id in self.prices
        }


class FakeUserCategoryFollowGateway:
    def __init__(self) -> None:
        self.users_by_category: dict[UUID, list[User]] = {}
        self.requested_categories: list[UUID] = []

    async def get_users_followed_to_category(
        self,
        category_id: UUID,
    ) -> list[User]:
        self.requested_categories.append(category_id)
        return self.users_by_category.get(category_id, [])
