import logging

from datetime import UTC, datetime
from uuid import UUID

from lansly.auth.interfaces import IdProvider
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.preferences.consts import (
    MAX_FREE_CATEGORIES,
    MAX_FREE_STOP_WORDS,
    MAX_LENGTH_STOP_WORD,
    MAX_PRICE_FILTER_VALUE,
    MAX_PRO_CATEGORIES,
    MAX_PRO_STOP_WORDS,
    MIN_PRICE_FILTER_VALUE,
)
from lansly.preferences.dto import (
    CategoryWithFollowedStatusDTO,
    CountStopWordsDTO,
    DirectionWithFollowCountsDTO,
    FollowCategoryDTO,
    StopWordsDTO,
    SubcategoriesWithFollowStatusDTO,
)
from lansly.preferences.exceptions import (
    UserCategoryFollowAlreadyExistsError,
    UserCategoryFollowLimitExceededError,
)
from lansly.preferences.gateways import (
    UserCategoryFollowGateway,
    UserStopWordsGateway,
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
from lansly.preferences.validators import (
    freelancer_profile_about_validator,
    price_filter_range_validator,
)
from lansly.projects.exceptions import ProjectCategoryNotFoundError
from lansly.projects.models import ProjectCategory
from lansly.subscriptions.interfaces import (
    SubscriptionChecker,
)

logger = logging.getLogger(__name__)


class UserCategoryFollowService:
    def __init__(
        self,
        follow_gateway: UserCategoryFollowGateway,
        subscription_checker: SubscriptionChecker,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.follow_gateway = follow_gateway
        self.subscription_checker = subscription_checker
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def _get_subcategories_with_follow_status(
        self,
        user_id: UUID,
        parent_id: UUID,
    ) -> list[CategoryWithFollowedStatusDTO]:
        rows = await self.follow_gateway.get_subcategories_with_follow_status(
            user_id=user_id,
            parent_id=parent_id,
        )
        return [
            CategoryWithFollowedStatusDTO(category=row[0], is_followed=row[1])
            for row in rows
        ]

    async def get_directions_with_follow_counts(
        self,
        source: str,
    ) -> list[DirectionWithFollowCountsDTO]:
        user_id = await self.id_provider.get_current_user_id()
        rows = await self.follow_gateway.get_directions_with_follow_counts(
            user_id=user_id,
            source=source,
        )
        return [
            DirectionWithFollowCountsDTO(
                id=direction_id,
                title=title,
                followed_count=followed_count,
                total_count=total_count,
            )
            for direction_id, title, followed_count, total_count in rows
        ]

    async def get_subcategories_with_follow_status(
        self,
        parent_id: UUID,
    ) -> list[CategoryWithFollowedStatusDTO]:
        user_id = await self.id_provider.get_current_user_id()
        return await self._get_subcategories_with_follow_status(
            user_id=user_id,
            parent_id=parent_id,
        )

    async def _get_followed_categories(
        self,
        user_id: UUID,
    ) -> list[ProjectCategory]:
        follows = await self.follow_gateway.get_follows_with_category(user_id)
        return [follow.category for follow in follows]

    async def get_followed_categories(self) -> list[ProjectCategory]:
        user_id = await self.id_provider.get_current_user_id()
        return await self._get_followed_categories(user_id)

    async def unfollow_all_categories(self) -> list[ProjectCategory]:
        user_id = await self.id_provider.get_current_user_id()
        await self.follow_gateway.deactivate_all(user_id)
        await self.transaction_manager.commit()
        return await self._get_followed_categories(user_id)

    async def _get_user_limit_and_available(self, user_id: UUID) -> int:
        is_pro_user = await self.subscription_checker.is_pro_user(user_id)
        return MAX_FREE_CATEGORIES if not is_pro_user else MAX_PRO_CATEGORIES

    # TODO: все методы подписки и отписки категорий,
    # добавить защиту от race condition
    async def toggle_category_follow(
        self,
        category_id: UUID,
    ) -> SubcategoriesWithFollowStatusDTO:
        user_id = await self.id_provider.get_current_user_id()
        category = await self.follow_gateway.get_category(category_id)
        if category is None or category.parent_id is None:
            raise ProjectCategoryNotFoundError
        follow = await self.follow_gateway.get(
            user_id=user_id,
            category_id=category_id,
        )
        now = datetime.now(UTC)
        limit = await self._get_user_limit_and_available(user_id)

        if follow:
            if follow.is_active:
                follow.is_active = False
            else:
                count = (
                    await self.follow_gateway.get_count_followed_categories(
                        user_id,
                    )
                )
                if count + 1 > limit:
                    raise UserCategoryFollowLimitExceededError(limit=limit)
                follow.is_active = True
            follow.updated_at = now
            await self.transaction_manager.commit()
        else:
            count = await self.follow_gateway.get_count_followed_categories(
                user_id,
            )
            if count + 1 > limit:
                raise UserCategoryFollowLimitExceededError(limit=limit)
            new_follow = UserCategoryFollow(
                user_id=user_id,
                category_id=category_id,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            try:
                await self.follow_gateway.add(new_follow)
                await self.transaction_manager.commit()
            except UserCategoryFollowAlreadyExistsError:
                logger.info(
                    "UserCategoryFollow Already Exists "
                    f"user_id={user_id}, category_id={category_id}",
                )
        # parent_id переработать метод и забирать из UserCategoryFollow
        subcategories = await self._get_subcategories_with_follow_status(
            user_id=user_id,
            parent_id=category.parent_id,
        )
        return SubcategoriesWithFollowStatusDTO(
            categories=subcategories,
            limit=limit,
        )

    async def follow_category(
        self,
        category_id: UUID,
    ) -> FollowCategoryDTO:
        user_id = await self.id_provider.get_current_user_id()

        category = await self.follow_gateway.get_category(category_id)
        if category is None or category.parent_id is None:
            raise ProjectCategoryNotFoundError

        follow = await self.follow_gateway.get(
            user_id=user_id,
            category_id=category_id,
        )
        if follow is not None and follow.is_active:
            return FollowCategoryDTO(
                category_id=category.id,
                title=category.title,
            )

        limit = await self._get_user_limit_and_available(user_id)
        followed_count = (
            await self.follow_gateway.get_count_followed_categories(user_id)
        )
        if followed_count >= limit:
            raise UserCategoryFollowLimitExceededError(limit=limit)

        now = datetime.now(UTC)
        if follow is not None:
            follow.is_active = True
            follow.updated_at = now
        else:
            follow = UserCategoryFollow(
                user_id=user_id,
                category_id=category_id,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            await self.follow_gateway.add(follow)
        await self.transaction_manager.commit()
        return FollowCategoryDTO(
            category_id=category.id,
            title=category.title,
        )


class UserFreelancerProfileService:
    def __init__(
        self,
        profile_gateway: FreelancerProfileGateway,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.profile_gateway = profile_gateway
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def get_profile(self) -> UserFreelancerProfile | None:
        user_id = await self.id_provider.get_current_user_id()
        return await self.profile_gateway.get(user_id)

    async def edit_or_create_profile(
        self,
        about_text: str,
    ) -> UserFreelancerProfile:
        user_id = await self.id_provider.get_current_user_id()
        freelancer_profile_about_validator(about_text)
        profile = await self.profile_gateway.get(user_id)
        if profile is not None:
            profile.about = about_text
        else:
            profile = UserFreelancerProfile(
                user_id=user_id,
                about=about_text,
            )
            await self.profile_gateway.add(profile)
        await self.transaction_manager.commit()
        return profile


class UserStopWordsService:
    def __init__(
        self,
        stop_words_gateway: UserStopWordsGateway,
        subscription_checker: SubscriptionChecker,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.stop_words_gateway = stop_words_gateway
        self.subscription_checker = subscription_checker
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def _get_user_limit_and_available(
        self,
        user_id: UUID,
        current_count: int,
    ) -> tuple[int, int]:
        is_pro_user = await self.subscription_checker.is_pro_user(user_id)
        limit = MAX_FREE_STOP_WORDS if not is_pro_user else MAX_PRO_STOP_WORDS
        available = max(limit - current_count, 0)
        return limit, available

    async def add_stop_words(self, words: list[str]) -> StopWordsDTO:
        logger.debug(f"ADD STOP WORDS LIST: {words}")
        user_id = await self.id_provider.get_current_user_id()
        current_stop_words = (
            await self.stop_words_gateway.get_stop_words_by_user_id(
                user_id,
            )
        )
        limit, available = await self._get_user_limit_and_available(
            user_id=user_id,
            current_count=len(current_stop_words),
        )
        if available == 0:
            return StopWordsDTO(
                words=current_stop_words,
                available=available,
                limit=limit,
            )
        now = datetime.now(UTC)
        new_stop_words = [
            UserStopWord(
                user_id=user_id,
                word=word.lower().strip(),
                created_at=now,
            )
            for word in words
            if word.strip()
            and len(word.strip()) <= MAX_LENGTH_STOP_WORD
            and word.lower().strip() not in current_stop_words
        ]
        new_stop_words = new_stop_words[:available]
        if new_stop_words:
            await self.stop_words_gateway.add_batch(new_stop_words)
            await self.transaction_manager.commit()
        full_stop_words = (
            await self.stop_words_gateway.get_stop_words_by_user_id(
                user_id,
            )
        )
        limit, available = await self._get_user_limit_and_available(
            user_id=user_id,
            current_count=len(full_stop_words),
        )
        return StopWordsDTO(
            words=full_stop_words,
            available=available,
            limit=limit,
        )

    async def delete_stop_words(self, words: list[str]) -> StopWordsDTO:
        user_id = await self.id_provider.get_current_user_id()
        stop_words = [word.lower().strip() for word in words]
        if stop_words:
            await self.stop_words_gateway.delete_batch(user_id, stop_words)
            await self.transaction_manager.commit()
        new_stop_words = (
            await self.stop_words_gateway.get_stop_words_by_user_id(user_id)
        )
        limit, available = await self._get_user_limit_and_available(
            user_id=user_id,
            current_count=len(new_stop_words),
        )
        return StopWordsDTO(
            words=new_stop_words,
            available=available,
            limit=limit,
        )

    async def get_stop_words(self) -> StopWordsDTO:
        user_id = await self.id_provider.get_current_user_id()
        stop_words = await self.stop_words_gateway.get_stop_words_by_user_id(
            user_id,
        )
        limit, available = await self._get_user_limit_and_available(
            user_id,
            current_count=len(stop_words),
        )
        return StopWordsDTO(
            words=stop_words,
            available=available,
            limit=limit,
        )

    async def count_stop_words(self) -> CountStopWordsDTO:
        user_id = await self.id_provider.get_current_user_id()
        count = await self.stop_words_gateway.count_stop_words_by_user_id(
            user_id,
        )
        limit, available = await self._get_user_limit_and_available(
            user_id=user_id,
            current_count=count,
        )
        return CountStopWordsDTO(count=count, available=available, limit=limit)


class UserPriceFilterService:
    def __init__(
        self,
        gateway: UserPriceFilterGateway,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.gateway = gateway
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def get_price_filter(self) -> UserPriceFilter | None:
        user_id = await self.id_provider.get_current_user_id()
        return await self.gateway.get_by_user_id(user_id)

    async def set_price_filter(
        self,
        min_price: int,
        max_price: int,
    ) -> UserPriceFilter:
        min_price = max(min_price, MIN_PRICE_FILTER_VALUE)
        max_price = min(max_price, MAX_PRICE_FILTER_VALUE)
        price_filter_range_validator(min_price=min_price, max_price=max_price)
        user_id = await self.id_provider.get_current_user_id()
        now = datetime.now(UTC)
        price_filter = UserPriceFilter(
            user_id=user_id,
            min_price=min_price,
            max_price=max_price,
            created_at=now,
            updated_at=now,
        )
        await self.gateway.upsert(price_filter)
        await self.transaction_manager.commit()
        return price_filter

    async def clear_price_filter(self) -> None:
        user_id = await self.id_provider.get_current_user_id()
        await self.gateway.delete_by_user_id(user_id=user_id)
        await self.transaction_manager.commit()
