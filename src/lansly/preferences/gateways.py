from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import functions

from lansly.preferences.exceptions import (
    UserCategoryFollowAlreadyExistsError,
    UserCategoryFollowCreationError,
)
from lansly.preferences.interfaces import (
    FreelancerProfileGateway,
    UserPriceFilterGateway,
)
from lansly.preferences.models import (
    UserCategoryFollow,
    UserFreelancerProfile,
    UserPriceFilter,
    UserStopWord,
)
from lansly.projects.models import ProjectCategory
from lansly.users.models import User


class UserCategoryFollowGateway:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, follow: UserCategoryFollow):
        try:
            self.session.add(follow)
            await self.session.flush()
        except IntegrityError as exc:
            if (
                "already exists" in str(exc.orig)
                or "duplicate" in str(exc.orig).lower()
            ):
                raise UserCategoryFollowAlreadyExistsError
            raise UserCategoryFollowCreationError

    async def deactivate_all(self, user_id: UUID):
        stmt = (
            update(UserCategoryFollow)
            .values(
                {"is_active": False},
            )
            .where(UserCategoryFollow.user_id == user_id)
        )
        await self.session.execute(stmt)

    async def deactivate_excess_follows(
        self,
        user_id: UUID,
        keep_count: int,
    ) -> None:
        keep_ids_subq = (
            select(UserCategoryFollow.category_id)
            .where(
                UserCategoryFollow.user_id == user_id,
                UserCategoryFollow.is_active.is_(True),
            )
            .order_by(UserCategoryFollow.created_at.asc())
            .limit(keep_count)
            .scalar_subquery()
        )
        stmt = (
            update(UserCategoryFollow)
            .values({"is_active": False, "updated_at": datetime.now(UTC)})
            .where(
                UserCategoryFollow.user_id == user_id,
                UserCategoryFollow.is_active.is_(True),
                UserCategoryFollow.category_id.not_in(keep_ids_subq),
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)

    async def get(
        self,
        user_id: UUID,
        category_id: UUID,
    ) -> UserCategoryFollow | None:
        stmt = select(UserCategoryFollow).where(
            UserCategoryFollow.user_id == user_id,
            UserCategoryFollow.category_id == category_id,
        )
        return await self.session.scalar(stmt)

    async def get_category(
        self,
        category_id: UUID,
    ) -> ProjectCategory | None:
        stmt = (
            select(ProjectCategory)
            .where(ProjectCategory.id == category_id)
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def get_count_followed_categories(self, user_id: UUID) -> int:
        stmt = select(functions.count(UserCategoryFollow.user_id)).where(
            UserCategoryFollow.user_id == user_id,
            UserCategoryFollow.is_active.is_(True),
        )
        result = await self.session.scalar(stmt)
        if result is None:
            return 0
        return result

    async def get_follows_with_category(
        self,
        user_id: UUID,
    ) -> list[UserCategoryFollow]:
        stmt = (
            select(UserCategoryFollow)
            .options(joinedload(UserCategoryFollow.category))
            .where(
                UserCategoryFollow.user_id == user_id,
                UserCategoryFollow.is_active.is_(True),
            )
        )
        return list(await self.session.scalars(stmt))

    async def get_subcategories_with_follow_status(
        self,
        user_id: UUID,
        parent_id: UUID,
    ) -> list[tuple[ProjectCategory, bool]]:
        stmt = (
            select(
                ProjectCategory,
                UserCategoryFollow.user_id.is_not(None).label("is_followed"),
            )
            .outerjoin(
                UserCategoryFollow,
                and_(
                    ProjectCategory.id == UserCategoryFollow.category_id,
                    UserCategoryFollow.user_id == user_id,
                    UserCategoryFollow.is_active.is_(True),
                ),
            )
            .where(ProjectCategory.parent_id == parent_id)
            .order_by(ProjectCategory.id)
        )
        result = await self.session.execute(stmt)
        return list(result.tuples().all())

    async def get_users_followed_to_category(
        self,
        category_id: UUID,
    ) -> list[User]:
        stmt = (
            select(User)
            .join(
                UserCategoryFollow,
                and_(
                    UserCategoryFollow.user_id == User.id,
                    UserCategoryFollow.is_active.is_(True),
                ),
            )
            .where(UserCategoryFollow.category_id == category_id)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())


class SAFreelancerProfileGateway(FreelancerProfileGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, profile: UserFreelancerProfile) -> None:
        self.session.add(profile)
        await self.session.flush()

    async def get(self, user_id: UUID) -> UserFreelancerProfile | None:
        stmt = select(UserFreelancerProfile).where(
            UserFreelancerProfile.user_id == user_id,
        )
        return await self.session.scalar(stmt)


class UserStopWordsGateway:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_batch(self, words: list[UserStopWord]):
        values = [
            {
                "user_id": word.user_id,
                "word": word.word,
                "created_at": word.created_at,
            }
            for word in words
        ]
        stmt = (
            pg_insert(UserStopWord)
            .values(values)
            .on_conflict_do_nothing(index_elements=["user_id", "word"])
        )
        await self.session.execute(stmt)

    async def delete_batch(self, user_id: UUID, words: list[str]):
        stmt = delete(UserStopWord).where(
            and_(
                UserStopWord.user_id == user_id,
                UserStopWord.word.in_(words),
            ),
        )
        await self.session.execute(stmt)

    async def delete_excess(self, user_id: UUID, keep_count: int) -> None:
        keep_words_subq = (
            select(UserStopWord.word)
            .where(
                UserStopWord.user_id == user_id,
            )
            .order_by(UserStopWord.created_at.asc())
            .limit(keep_count)
            .scalar_subquery()
        )
        stmt = delete(UserStopWord).where(
            UserStopWord.user_id == user_id,
            UserStopWord.word.not_in(keep_words_subq),
        )
        await self.session.execute(stmt)

    async def get_stop_words_by_user_id(self, user_id: UUID) -> list[str]:
        stmt = (
            select(UserStopWord.word)
            .where(UserStopWord.user_id == user_id)
            .order_by(UserStopWord.created_at.asc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [row[0] for row in rows]

    async def count_stop_words_by_user_id(self, user_id: UUID) -> int:
        stmt = select(functions.count(UserStopWord.word)).where(
            UserStopWord.user_id == user_id,
        )
        result = await self.session.scalar(stmt)
        if result is None:
            return 0
        return result

    async def get_stop_words_by_user_ids(
        self,
        user_ids: list[UUID],
    ) -> dict[UUID, list[str]]:
        if not user_ids:
            return {}
        stmt = (
            select(UserStopWord.user_id, UserStopWord.word)
            .where(UserStopWord.user_id.in_(user_ids))
            .order_by(UserStopWord.created_at.asc())
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        stop_words_map: dict[UUID, list[str]] = {}
        for user_id, word in rows:
            stop_words_map.setdefault(user_id, []).append(word)
        return stop_words_map


class SAUserPriceFilterGateway(UserPriceFilterGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, price_filter: UserPriceFilter) -> None:
        stmt = (
            pg_insert(UserPriceFilter)
            .values(
                user_id=price_filter.user_id,
                min_price=price_filter.min_price,
                max_price=price_filter.max_price,
                created_at=price_filter.created_at,
                updated_at=price_filter.updated_at,
            )
            .on_conflict_do_update(
                index_elements=[UserPriceFilter.user_id],
                set_={
                    "min_price": price_filter.min_price,
                    "max_price": price_filter.max_price,
                    "updated_at": price_filter.updated_at,
                },
            )
        )
        await self.session.execute(stmt)

    async def delete_by_user_id(self, user_id: UUID) -> None:
        stmt = delete(UserPriceFilter).where(
            UserPriceFilter.user_id == user_id,
        )
        await self.session.execute(stmt)

    async def get_by_user_id(self, user_id: UUID) -> UserPriceFilter | None:
        stmt = (
            select(UserPriceFilter)
            .where(UserPriceFilter.user_id == user_id)
        )
        return await self.session.scalar(stmt)

    async def get_filter_by_user_ids(
        self,
        user_ids: list[UUID],
    ) -> dict[UUID, tuple[int, int]]:
        stmt = select(
            UserPriceFilter.user_id,
            UserPriceFilter.min_price,
            UserPriceFilter.max_price,
        ).where(UserPriceFilter.user_id.in_(user_ids))
        result = await self.session.execute(stmt)
        rows = result.all()
        price_filters_map: dict[UUID, tuple[int, int]] = {}
        for user_id, min_price, max_price in rows:
            price_filters_map[user_id] = (min_price, max_price)
        return price_filters_map
