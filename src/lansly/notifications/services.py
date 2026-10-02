import asyncio
import logging

from datetime import UTC, datetime
from uuid import UUID

from lansly.apps.telegram_bot.keyboards import (
    build_channel_project_kbd,
    build_no_active_subscription_kbd,
    build_project_kbd,
    build_subscription_activated_kbd,
)
from lansly.apps.telegram_bot.messages import (
    flru_project_message,
    generating_proposal_failed_message,
    kwork_project_message,
)
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.infra.telegram.telegram_notifier import TelegramNotifier
from lansly.notifications.exceptions import (
    ProjectNotificationDeliveryError,
    RecipientUnavailableError,
)
from lansly.notifications.interfaces import (
    ChannelNotificationGateway,
    ProjectNotificationGateway,
)
from lansly.notifications.models import (
    ChannelNotification,
    ProjectNotification,
)
from lansly.preferences.gateways import (
    UserCategoryFollowGateway,
    UserStopWordsGateway,
)
from lansly.preferences.interfaces import UserPriceFilterGateway
from lansly.projects.consts import Marketplace
from lansly.projects.dto import ProjectLinks
from lansly.projects.exceptions import ProjectProposalNotFoundError
from lansly.projects.gateways import ProjectProposalGateway
from lansly.projects.interfaces import ProjectGateway
from lansly.projects.models import Project
from lansly.projects.urls import MarketplaceUrlBuilder
from lansly.users.exceptions import UserNotFoundError
from lansly.users.interfaces import UserGateway

logger = logging.getLogger(__name__)


class ProjectNotificationService:
    def __init__(  # noqa: PLR0917
        self,
        project_gateway: ProjectGateway,
        follow_gateway: UserCategoryFollowGateway,
        stop_words_gateway: UserStopWordsGateway,
        price_filter_gateway: UserPriceFilterGateway,
        project_notification_gateway: ProjectNotificationGateway,
        channel_notification_gateway: ChannelNotificationGateway,
        telegram_notifier: TelegramNotifier,
        transaction_manager: TransactionManager,
        url_builder: MarketplaceUrlBuilder,
        channel_id: int | None = None,
    ):
        self.project_gateway = project_gateway
        self.follow_gateway = follow_gateway
        self.stop_words_gateway = stop_words_gateway
        self.price_filter_gateway = price_filter_gateway
        self.project_notification_gateway = project_notification_gateway
        self.channel_notification_gateway = channel_notification_gateway
        self.telegram_notifier = telegram_notifier
        self.transaction_manager = transaction_manager
        self.url_builder = url_builder
        self.channel_id = channel_id

    def _contains_stop_word(self, text: str, stop_words: list[str]) -> bool:
        if not stop_words:
            return False
        text_lower = text.lower()
        return any(sw.lower() in text_lower for sw in stop_words)

    def _get_project_message(
        self,
        project: Project,
        links: ProjectLinks,
    ) -> str:
        if project.source == Marketplace.KWORK:
            return kwork_project_message(project, links)
        if project.source == Marketplace.FL:
            return flru_project_message(project, links)
        raise ValueError("Project source not supported")

    async def notify_new_projects(  # noqa: C901, PLR0912
        self,
        project_ids: list[UUID],
    ) -> None:
        projects = await self.project_gateway.get_projects_by_ids(
            project_ids,
            with_category=True,
            with_customer=True,
        )
        logger.info(f"NOTIFY NEW PROJECTS: {projects}")

        has_delivery_errors = False

        for project in projects:
            if project.category_id is None:
                continue
            project_notifications: list[ProjectNotification] = []
            users = await self.follow_gateway.get_users_followed_to_category(
                project.category_id,
            )
            user_ids = [user.id for user in users]
            stop_words_map = (
                await self.stop_words_gateway.get_stop_words_by_user_ids(
                    user_ids,
                )
            )
            price_filter_map = (
                await self.price_filter_gateway.get_filter_by_user_ids(
                    user_ids,
                )
            )
            project_text = f"{project.title} {project.description}"
            for user in users:
                if user.telegram_id is None:
                    continue
                if user.is_telegram_unavailable:
                    logger.info(
                        f"User with telegram_id={user.telegram_id} "
                        "telegram unavailable",
                    )
                    continue
                user_stop_words = stop_words_map.get(user.id, [])
                if self._contains_stop_word(project_text, user_stop_words):
                    continue
                price_filter = price_filter_map.get(user.id)
                if price_filter is not None:
                    min_price = price_filter[0]
                    max_price = price_filter[1]
                    if min_price > project.price or project.price > max_price:
                        continue

                previous_notification = (
                    await self.project_notification_gateway.get(
                        project_id=project.id,
                        user_id=user.id,
                    )
                )
                if (
                    previous_notification is not None
                    and previous_notification.error is None
                    and previous_notification.project_updated_at
                    >= project.updated_at
                ):
                    continue

                notification = ProjectNotification(
                    project_id=project.id,
                    user_id=user.id,
                    project_updated_at=project.updated_at,
                    sent_at=datetime.now(UTC),
                    error=None,
                )
                try:
                    project_links = self.url_builder.build_links(project)
                    await self.telegram_notifier.send_message(
                        chat_id=user.telegram_id,
                        text=self._get_project_message(
                            project,
                            project_links,
                        ),
                        keyboard=build_project_kbd(project, project_links),
                    )
                except RecipientUnavailableError as exc:
                    notification.error = str(exc)
                    user.mark_telegram_unavailable()
                    await self.transaction_manager.flush()
                except Exception as exc:
                    notification.error = str(exc)
                    has_delivery_errors = True
                    logger.exception(
                        "Failed to notify user %s about project %s",
                        user.id,
                        project.id,
                    )
                project_notifications.append(notification)
                await asyncio.sleep(0.3)

            if project_notifications:
                await self.project_notification_gateway.bulk_upsert(
                    project_notifications,
                )
                await self.transaction_manager.commit()

        if has_delivery_errors:
            raise ProjectNotificationDeliveryError(
                "Some project notifications were not delivered",
            )

    async def notify_new_projects_to_channel(
        self,
        project_ids: list[UUID],
    ):
        if self.channel_id is None:
            logger.warning("TELEGRAM_CHANNEL_ID not configured")
            return
        min_price = 30000
        projects = await self.project_gateway.get_projects_by_ids(
            project_ids=project_ids,
            with_category=True,
            with_customer=True,
        )
        high_value_projects = [pr for pr in projects if pr.price >= min_price]
        logger.info(f"NOTIFY NEW PROJECTS TO CHANNEL: {high_value_projects}")
        channel_notifications = []
        for project in high_value_projects:
            if project.category_id is None:
                continue
            try:
                project_links = self.url_builder.build_links(project)
                await self.telegram_notifier.send_message(
                    chat_id=self.channel_id,
                    text=self._get_project_message(
                        project,
                        project_links,
                    ),
                    keyboard=build_channel_project_kbd(project_links),
                )
                channel_notifications.append(
                    ChannelNotification(
                        project_id=project.id,
                        sent_at=datetime.now(UTC),
                    ),
                )
            except Exception:
                logger.exception(
                    f"Failed to send message to channel: {self.channel_id}",
                )
        if channel_notifications:
            await self.channel_notification_gateway.bulk_insert(
                channel_notifications,
            )
            await self.transaction_manager.commit()


class ProjectProposalNotificationService:
    def __init__(
        self,
        user_gateway: UserGateway,
        proposal_gateway: ProjectProposalGateway,
        telegram_notifier: TelegramNotifier,
    ):
        self.user_gateway = user_gateway
        self.proposal_gateway = proposal_gateway
        self.telegram_notifier = telegram_notifier

    async def notify_generated(self, user_id: UUID, project_id: UUID):
        logger.info(
            f"NOTIFY PROJECT PROPOSAL: user_id={user_id}, "
            f"project_id: {project_id}",
        )
        proposal = await self.proposal_gateway.get_with_user(
            user_id=user_id,
            project_id=project_id,
        )
        if not proposal:
            raise ProjectProposalNotFoundError

        await self.telegram_notifier.send_message(
            chat_id=proposal.user.telegram_id,
            text=proposal.generated_text,
        )

    async def notify_generated_failed(self, user_id: UUID):
        user = await self.user_gateway.get_by_id(user_id)
        if user is None:
            return
        await self.telegram_notifier.send_message(
            chat_id=user.telegram_id,
            text=generating_proposal_failed_message(),
        )


class SubscriptionNotificationService:
    def __init__(
        self,
        user_gateway: UserGateway,
        telegram_notifier: TelegramNotifier,
    ):
        self.user_gateway = user_gateway
        self.telegram_notifier = telegram_notifier

    async def notify_activated(self, user_id: UUID):
        user = await self.user_gateway.get_by_id(user_id)
        if not user:
            raise UserNotFoundError
        await self.telegram_notifier.send_message(
            chat_id=user.telegram_id,
            text="👑 PRO подписка активирована!",
            keyboard=build_subscription_activated_kbd(),
        )

    async def notify_renewed(self, user_id: UUID, new_expires_at: datetime):
        user = await self.user_gateway.get_by_id(user_id)
        await self.telegram_notifier.send_message(
            chat_id=user.telegram_id,
            text=(
                f"✅ PRO подписка продлена до "
                f"{new_expires_at.strftime('%d.%m.%Y')}"
            ),
        )

    async def notify_retry(self, user_id: UUID):
        user = await self.user_gateway.get_by_id(user_id)
        await self.telegram_notifier.send_message(
            chat_id=user.telegram_id,
            text="⚠️ Не удалось списать оплату за подписку.",
        )

    async def notify_revoked(self, user_id: UUID):
        user = await self.user_gateway.get_by_id(user_id)
        await self.telegram_notifier.send_message(
            chat_id=user.telegram_id,
            text="❌ PRO доступ отключён за неуплату",
            keyboard=build_no_active_subscription_kbd(),
        )
