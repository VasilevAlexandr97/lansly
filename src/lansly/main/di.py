from collections.abc import AsyncIterable
from typing import Any

from aiogram import Bot
from aiogram.types import TelegramObject
from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    make_async_container,
    provide,
)
from fastapi import Request
from fastapi.templating import Jinja2Templates
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from lansly.apps.web.sitemap.builder import SitemapBuilder
from lansly.apps.web.sitemap.sections import (
    ArticlesSitemapSection,
    StaticSitemapSection,
)
from lansly.articles.gateways import SAArticleGateway, SAArticleImageGateway
from lansly.articles.interfaces import ArticleGateway, ArticleImageGateway
from lansly.articles.service import ArticleService
from lansly.auth.id_provider import (
    SessionIdProvider,
    TelegramIdProvider,
    WebIdProvider,
    WorkerIdProvider,
)
from lansly.auth.interfaces import (
    IdProvider,
    SessionManager,
    SessionStorage,
    SessionTransport,
)
from lansly.auth.log_in import LogIn
from lansly.auth.log_out import LogOut
from lansly.auth.session_manager import SessionManagerImpl
from lansly.auth.session_storage import RedisSessionStorage
from lansly.auth.session_transport import FastAPISessionTransport
from lansly.auth.telegram_auth import TelegramAuth
from lansly.common.dto import CurrentUser
from lansly.common.interfaces.llm_client import LLMClient
from lansly.common.interfaces.password_hasher import PasswordHasher
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.common.password_hasher_bcrypt import PasswordHasherBcrypt
from lansly.infra.database.transaction_manager import SATransactionManager
from lansly.infra.kwork.client import KworkClient
from lansly.infra.polza.client import PolzaClient
from lansly.infra.polza.limiter import PolzaRateLimiter
from lansly.infra.taskiq.queue import (
    TaskiqProposalGeneratedNotificationQueue,
    TaskiqProposalGenerationQueue,
    TaskiqSubscriptionActivatedNotificationQueue,
    TaskiqSubscriptionRenewalNotificationQueue,
)
from lansly.infra.telegram.telegram_notifier import TelegramNotifier
from lansly.infra.yookassa.client import YooKassaClient
from lansly.infra.yookassa.limiter import YookassaRateLimiter
from lansly.main.config import Config
from lansly.notifications.gateways import (
    SAChannelNotificationGateway,
    SAProjectNotificationGateway,
)
from lansly.notifications.interfaces import (
    ChannelNotificationGateway,
    ProjectNotificationGateway,
    ProposalGeneratedNotificationQueue,
    SubscriptionActivatedNotificationQueue,
    SubscriptionRenewalNotificationQueue,
)
from lansly.notifications.services import (
    ProjectNotificationService,
    ProjectProposalNotificationService,
    SubscriptionNotificationService,
)
from lansly.preferences.gateways import (
    SAFreelancerProfileGateway,
    SAUserPriceFilterGateway,
    UserCategoryFollowGateway,
    UserStopWordsGateway,
)
from lansly.preferences.interfaces import (
    FreelancerProfileGateway,
    UserPriceFilterGateway,
)
from lansly.preferences.services import (
    UserCategoryFollowService,
    UserFreelancerProfileService,
    UserPriceFilterService,
    UserStopWordsService,
)
from lansly.projects.gateways import (
    ProjectProposalGateway,
    ProjectProposalRequestGateway,
    SAProjectCategoryGateway,
    SAProjectGateway,
    SAUserGenerationUsageGateway,
    UserGenerationUsageGateway,
)
from lansly.projects.generators import ProjectProposalGenerator
from lansly.projects.interfaces import (
    GenerationLimitChecker,
    ProjectCategoryGateway,
    ProjectGateway,
    ProposalGenerationQueue,
)
from lansly.projects.services import (
    ProjectCategoryService,
    ProjectProposalGenerationService,
    ProjectProposalRequestService,
    ProjectSyncService,
)
from lansly.projects.usage_checker import GenerationLimitCheckerImpl
from lansly.statistics.gateways import (
    SADailyMetricsGateway,
    SAProjectDailyStatsGateway,
)
from lansly.statistics.interfaces import (
    DailyMetricsGateway,
    ProjectDailyStatsGateway,
)
from lansly.statistics.services import DailyMetricsService
from lansly.subscriptions.checker import (
    SubscriptionCheckerImpl,
)
from lansly.subscriptions.gateways import (
    PaymentGateway,
    SubscriptionGateway,
    SubscriptionPlanGateway,
)
from lansly.subscriptions.interfaces import (
    SubscriptionChecker,
    SubscriptionLimitsResetter,
)
from lansly.subscriptions.limits_resetter import (
    SubscriptionLimitsResetterImpl,
)
from lansly.subscriptions.services import (
    PaymentVerificationService,
    SubscriptionManagementService,
    SubscriptionPaymentService,
    SubscriptionRenewalService,
)
from lansly.users.gateways import (
    SAUserGateway,
    SAUserRoleGateway,
)
from lansly.users.interfaces import UserGateway, UserRoleGateway
from lansly.users.service import CreateAdminUserService


class InfraProvider(Provider):
    @provide(scope=Scope.APP)
    def get_engine(self, config: Config) -> AsyncEngine:
        return create_async_engine(config.postgres.connection_url)

    @provide(scope=Scope.APP)
    def get_session_maker(
        self,
        engine: AsyncEngine,
    ) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
        )

    @provide(scope=Scope.REQUEST)
    async def get_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> AsyncIterable[AsyncSession]:
        async with session_maker() as session:
            yield session

    @provide(scope=Scope.REQUEST, provides=TransactionManager)
    def get_transaction_manager(
        self,
        session: AsyncSession,
    ) -> SATransactionManager:
        return SATransactionManager(session)

    @provide(scope=Scope.APP)
    def get_redis_pool(self, config: Config) -> ConnectionPool:
        return ConnectionPool.from_url(
            config.redis.connection_url,
            max_connections=20,  # Пул из 20 соединений
            decode_responses=True,
            retry_on_timeout=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            socket_keepalive=True,
            health_check_interval=30,
        )

    @provide(scope=Scope.APP)
    async def get_redis_client(
        self,
        pool: ConnectionPool,
    ) -> AsyncIterable[Redis]:
        client = Redis(connection_pool=pool)
        yield client
        await client.aclose(close_connection_pool=True)

    @provide(scope=Scope.APP)
    def get_kwork_client(self, config: Config) -> KworkClient:
        return KworkClient(
            login=config.kwork.login,
            password=config.kwork.password,
        )

    @provide(scope=Scope.APP)
    def get_telegram_notifier(self, bot: Bot) -> TelegramNotifier:
        return TelegramNotifier(bot=bot)

    @provide(scope=Scope.APP)
    def get_yookassa_rate_limiter(
        self,
        config: Config,
    ) -> YookassaRateLimiter:
        return YookassaRateLimiter(
            shop_id=config.yookassa.shop_id,
            redis_uri=config.redis.async_connection_url,
            limit_per_minute=100,
        )

    @provide(scope=Scope.APP)
    async def get_yookassa_client(
        self,
        config: Config,
        limiter: YookassaRateLimiter,
    ) -> AsyncIterable[YooKassaClient]:
        client = YooKassaClient(
            shop_id=config.yookassa.shop_id,
            secret_key=config.yookassa.secret_key,
            limiter=limiter,
        )
        yield client
        await client.close()

    @provide(scope=Scope.APP)
    def get_polza_rate_limiter(
        self,
        config: Config,
    ) -> PolzaRateLimiter:
        return PolzaRateLimiter(
            redis_uri=config.redis.async_connection_url,
            limit_per_minute=180,
        )

    @provide(scope=Scope.APP, provides=LLMClient)
    async def get_polza_client(
        self,
        config: Config,
        limiter: PolzaRateLimiter,
    ) -> AsyncIterable[PolzaClient]:
        client = PolzaClient(
            api_key=config.polza.api_key,
            base_url=config.polza.base_url,
            limiter=limiter,
        )
        yield client
        await client.close()


class AuthProvider(Provider):
    @provide(scope=Scope.APP, provides=PasswordHasher)
    def get_password_hasher(self) -> PasswordHasherBcrypt:
        return PasswordHasherBcrypt()


class ArticleProvider(Provider):
    article_gateway = provide(
        SAArticleGateway,
        scope=Scope.REQUEST,
        provides=ArticleGateway,
    )
    article_image_gateway = provide(
        SAArticleImageGateway,
        scope=Scope.REQUEST,
        provides=ArticleImageGateway,
    )
    article_service = provide(ArticleService, scope=Scope.REQUEST)


class UserProvider(Provider):
    user_gateway = provide(
        SAUserGateway,
        scope=Scope.REQUEST,
        provides=UserGateway,
    )
    user_role_gateway = provide(
        SAUserRoleGateway,
        scope=Scope.REQUEST,
        provides=UserRoleGateway,
    )

    @provide(scope=Scope.REQUEST)
    async def get_current_user(self, id_provider: IdProvider) -> CurrentUser:
        return await id_provider.get_current_user()

    create_admin_user_service = provide(
        CreateAdminUserService,
        scope=Scope.REQUEST,
    )


class ProjectProvider(Provider):
    project_category_gateway = provide(
        SAProjectCategoryGateway,
        scope=Scope.REQUEST,
        provides=ProjectCategoryGateway,
    )
    project_gateway = provide(
        SAProjectGateway,
        scope=Scope.REQUEST,
        provides=ProjectGateway,
    )
    project_proposal_gateway = provide(
        ProjectProposalGateway,
        scope=Scope.REQUEST,
    )
    project_proposal_request_gateway = provide(
        ProjectProposalRequestGateway,
        scope=Scope.REQUEST,
    )
    user_generation_usage_gateway = provide(
        SAUserGenerationUsageGateway,
        scope=Scope.REQUEST,
        provides=UserGenerationUsageGateway,
    )

    @provide(scope=Scope.REQUEST)
    async def get_project_proposal_generator(
        self,
        client: LLMClient,
    ) -> ProjectProposalGenerator:
        return ProjectProposalGenerator(client)

    @provide(scope=Scope.REQUEST)
    def get_project_category_service(
        self,
        gateway: ProjectCategoryGateway,
        transaction_manager: TransactionManager,
        kwork_client: KworkClient,
    ) -> ProjectCategoryService:
        return ProjectCategoryService(
            gateway=gateway,
            transaction_manager=transaction_manager,
            marketplace_client=kwork_client,
        )

    @provide(scope=Scope.REQUEST)
    def get_project_sync_service(
        self,
        category_gateway: ProjectCategoryGateway,
        project_gateway: ProjectGateway,
        transaction_manager: TransactionManager,
        kwork_client: KworkClient,
    ) -> ProjectSyncService:
        return ProjectSyncService(
            category_gateway=category_gateway,
            project_gateway=project_gateway,
            transaction_manager=transaction_manager,
            marketplace_client=kwork_client,
        )

    project_proposal_request_service = provide(
        ProjectProposalRequestService,
        scope=Scope.REQUEST,
    )
    project_proposal_generation_service = provide(
        ProjectProposalGenerationService,
        scope=Scope.REQUEST,
    )
    limit_checker = provide(
        GenerationLimitCheckerImpl,
        scope=Scope.REQUEST,
        provides=GenerationLimitChecker,
    )
    # TODO: подумать какой scope нужен для queue классов
    proposal_generation_queue = provide(
        TaskiqProposalGenerationQueue,
        scope=Scope.REQUEST,
        provides=ProposalGenerationQueue,
    )


class PreferenceProvider(Provider):
    user_category_follow_gateway = provide(
        UserCategoryFollowGateway,
        scope=Scope.REQUEST,
    )
    user_category_follow_service = provide(
        UserCategoryFollowService,
        scope=Scope.REQUEST,
    )
    freelancer_profile_gateway = provide(
        SAFreelancerProfileGateway,
        scope=Scope.REQUEST,
        provides=FreelancerProfileGateway,
    )
    user_freelancer_profile_service = provide(
        UserFreelancerProfileService,
        scope=Scope.REQUEST,
    )
    user_stop_words_gateway = provide(
        UserStopWordsGateway,
        scope=Scope.REQUEST,
    )
    user_stop_words_service = provide(
        UserStopWordsService,
        scope=Scope.REQUEST,
    )
    user_price_filter_gateway = provide(
        SAUserPriceFilterGateway,
        scope=Scope.REQUEST,
        provides=UserPriceFilterGateway,
    )
    user_price_filter_service = provide(
        UserPriceFilterService,
        scope=Scope.REQUEST,
    )


class NotificationProvider(Provider):
    project_notification_gateway = provide(
        SAProjectNotificationGateway,
        scope=Scope.REQUEST,
        provides=ProjectNotificationGateway,
    )
    channel_notification_gateway = provide(
        SAChannelNotificationGateway,
        scope=Scope.REQUEST,
        provides=ChannelNotificationGateway,
    )

    @provide(scope=Scope.REQUEST)
    async def get_project_notification_service(
        self,
        project_gateway: ProjectGateway,
        follow_gateway: UserCategoryFollowGateway,
        stop_words_gateway: UserStopWordsGateway,
        price_filter_gateway: UserPriceFilterGateway,
        project_notification_gateway: ProjectNotificationGateway,
        channel_notification_gateway: ChannelNotificationGateway,
        telegram_notifier: TelegramNotifier,
        transaction_manager: TransactionManager,
        redis: Redis,
        config: Config,
    ) -> ProjectNotificationService:
        return ProjectNotificationService(
            project_gateway=project_gateway,
            follow_gateway=follow_gateway,
            stop_words_gateway=stop_words_gateway,
            price_filter_gateway=price_filter_gateway,
            project_notification_gateway=project_notification_gateway,
            channel_notification_gateway=channel_notification_gateway,
            telegram_notifier=telegram_notifier,
            transaction_manager=transaction_manager,
            redis=redis,
            kwork_ref_id=config.kwork.ref_id,
            channel_id=config.telegram_channel_id,
        )

    project_proposal_notification_service = provide(
        ProjectProposalNotificationService,
        scope=Scope.REQUEST,
    )
    subscription_notification_service = provide(
        SubscriptionNotificationService,
        scope=Scope.REQUEST,
    )
    # TODO: подумать какой Scope нужен для Queue
    proposal_notification_queue = provide(
        TaskiqProposalGeneratedNotificationQueue,
        scope=Scope.REQUEST,
        provides=ProposalGeneratedNotificationQueue,
    )
    subscription_activated_notification_queue = provide(
        TaskiqSubscriptionActivatedNotificationQueue,
        scope=Scope.REQUEST,
        provides=SubscriptionActivatedNotificationQueue,
    )
    subscription_renewal_notification_queue = provide(
        TaskiqSubscriptionRenewalNotificationQueue,
        scope=Scope.REQUEST,
        provides=SubscriptionRenewalNotificationQueue,
    )


class SubscriptionProvider(Provider):
    subscription_plan_gateway = provide(
        SubscriptionPlanGateway,
        scope=Scope.REQUEST,
    )
    subscription_gateway = provide(
        SubscriptionGateway,
        scope=Scope.REQUEST,
    )
    payment_gateway = provide(
        PaymentGateway,
        scope=Scope.REQUEST,
    )
    subscription_payment_service = provide(
        SubscriptionPaymentService,
        scope=Scope.REQUEST,
    )
    subscription_management_service = provide(
        SubscriptionManagementService,
        scope=Scope.REQUEST,
    )
    subscription_renewal_service = provide(
        SubscriptionRenewalService,
        scope=Scope.REQUEST,
    )
    payment_verification_service = provide(
        PaymentVerificationService,
        scope=Scope.REQUEST,
    )
    subscription_checker = provide(
        SubscriptionCheckerImpl,
        scope=Scope.REQUEST,
        provides=SubscriptionChecker,
    )
    subscription_limits_resetter = provide(
        SubscriptionLimitsResetterImpl,
        scope=Scope.REQUEST,
        provides=SubscriptionLimitsResetter,
    )


class StatisticsProvider(Provider):
    daily_metrics_gateway = provide(
        SADailyMetricsGateway,
        scope=Scope.REQUEST,
        provides=DailyMetricsGateway,
    )
    project_daily_stats_gateway = provide(
        SAProjectDailyStatsGateway,
        scope=Scope.REQUEST,
        provides=ProjectDailyStatsGateway,
    )
    daily_metrics_service = provide(
        DailyMetricsService,
        scope=Scope.REQUEST,
    )


class TelegramBotProvider(Provider):
    @provide(scope=Scope.REQUEST, provides=IdProvider)
    def get_id_provider(
        self,
        event: TelegramObject,
        user_gateway: UserGateway,
        user_role_gateway: UserRoleGateway,
        sub_checker: SubscriptionChecker,
    ) -> TelegramIdProvider:
        return TelegramIdProvider(
            telegram_id=event.from_user.id,
            user_gateway=user_gateway,
            user_role_gateway=user_role_gateway,
            sub_checker=sub_checker,
        )

    telegram_auth = provide(TelegramAuth, scope=Scope.REQUEST)


class WorkerProvider(Provider):
    @provide(scope=Scope.REQUEST, provides=IdProvider)
    def get_id_provider(self) -> WorkerIdProvider:
        return WorkerIdProvider()


class AdminPanelProvider(Provider):
    @provide(scope=Scope.REQUEST, provides=IdProvider)
    def get_id_provider(
        self,
        request: Request,
        user_gateway: UserGateway,
        user_role_gateway: UserRoleGateway,
        sub_checker: SubscriptionChecker,
        session_manager: SessionManager,
    ) -> SessionIdProvider:
        return SessionIdProvider(
            request=request,
            user_gateway=user_gateway,
            user_role_gateway=user_role_gateway,
            sub_checker=sub_checker,
            session_manager=session_manager,
        )

    @provide(scope=Scope.REQUEST, provides=SessionStorage)
    def get_session_storage(self, redis_client: Redis) -> RedisSessionStorage:
        return RedisSessionStorage(redis_client)

    @provide(scope=Scope.REQUEST, provides=SessionTransport)
    def get_session_transport(
        self,
        request: Request,
    ) -> FastAPISessionTransport:
        return FastAPISessionTransport(request, session_key="__adm_s_id")

    @provide(scope=Scope.REQUEST, provides=SessionManager)
    def get_session_manager(
        self,
        session_storage: SessionStorage,
        session_transport: SessionTransport,
        config: Config,
    ) -> SessionManager:
        return SessionManagerImpl(
            session_storage=session_storage,
            session_transport=session_transport,
            ttl_seconds=config.admin_panel.session_ttl,
        )

    log_in = provide(LogIn, scope=Scope.REQUEST)
    log_out = provide(LogOut, scope=Scope.REQUEST)


class WebProvider(Provider):
    static_sitemap_section = provide(StaticSitemapSection, scope=Scope.REQUEST)
    articles_sitemap_section = provide(
        ArticlesSitemapSection,
        scope=Scope.REQUEST,
    )

    @provide(scope=Scope.REQUEST)
    def get_sitemap_builder(
        self,
        static_sitemap_section: StaticSitemapSection,
        articles_sitemap_section: ArticlesSitemapSection,
    ) -> SitemapBuilder:
        return SitemapBuilder(
            sections=[static_sitemap_section, articles_sitemap_section],
        )

    @provide(scope=Scope.REQUEST, provides=IdProvider)
    def get_id_provider(self) -> WebIdProvider:
        return WebIdProvider()

    @provide(scope=Scope.APP)
    def get_templates(self, config: Config) -> Jinja2Templates:
        return Jinja2Templates(directory=config.web.templates_dir)


def create_container(
    providers: list[Provider],
    context: dict[Any, Any] | None = None,
) -> AsyncContainer:
    return make_async_container(
        AuthProvider(),
        ArticleProvider(),
        InfraProvider(),
        UserProvider(),
        ProjectProvider(),
        PreferenceProvider(),
        NotificationProvider(),
        SubscriptionProvider(),
        StatisticsProvider(),
        *providers,
        context=context,
    )
