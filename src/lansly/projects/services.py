import html
import logging
import re
import traceback

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from lansly.auth.interfaces import IdProvider
from lansly.common.interfaces.lock_manager import DistributedLockManager
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.notifications.interfaces import (
    ProjectNotificationQueue,
    ProposalGeneratedNotificationQueue,
)
from lansly.preferences.exceptions import UserFreelancerProfileNotFoundError
from lansly.preferences.interfaces import FreelancerProfileGateway
from lansly.projects.consts import Marketplace
from lansly.projects.dto import (
    MarketplaceCategory,
    MarketplaceProject,
    ProjectProposalGenerationRequestResult,
    ProjectProposalGenerationRequestStatus,
)
from lansly.projects.exceptions import (
    GenerationLimitExceededError,
    MarketplaceIntegrationNotFoundError,
    ProjectNotFoundError,
    ProjectProposalGenerationError,
)
from lansly.projects.gateways import (
    ProjectProposalGateway,
    ProjectProposalRequestGateway,
    UserGenerationUsageGateway,
)
from lansly.projects.generators import ProjectProposalGenerator
from lansly.projects.integrations import MarketplaceIntegration
from lansly.projects.interfaces import (
    CustomerGateway,
    GenerationLimitChecker,
    MarketplaceClient,
    ProjectCategoryGateway,
    ProjectGateway,
    ProposalGenerationQueue,
)
from lansly.projects.models import (
    Customer,
    Project,
    ProjectCategory,
    ProjectProposal,
    ProjectProposalRequest,
    ProjectProposalRequestStatus,
)
from lansly.subscriptions.interfaces import SubscriptionChecker

logger = logging.getLogger(__name__)


class ProjectCategoryService:
    def __init__(
        self,
        clients: Sequence[MarketplaceClient],
        gateway: ProjectCategoryGateway,
        transaction_manager: TransactionManager,
    ):
        self.clients = clients
        self.gateway = gateway
        self.transaction_manager = transaction_manager

    async def import_categories(self) -> None:
        all_categories = await self._get_marketplace_categories()
        if not all_categories:
            return

        total = sum(1 + len(c.subcategories or []) for c in all_categories)
        logger.info(
            f"Fetched {total} categories "
            f"from {len(self.clients)} marketplaces",
        )

        by_source: dict[str, list[MarketplaceCategory]] = {}
        for cat in all_categories:
            by_source.setdefault(cat.source, []).append(cat)

        for source, cats in by_source.items():
            await self._import_for_source(source, cats)

        await self.transaction_manager.commit()

    async def get_root_categories(
        self,
        source: str | None = None,
    ) -> list[ProjectCategory]:
        return await self.gateway.get_root_categories(source)

    async def get_subcategories(
        self,
        parent_id: UUID,
    ) -> list[ProjectCategory]:
        return await self.gateway.get_subcategories(parent_id)

    async def _get_marketplace_categories(self) -> list[MarketplaceCategory]:
        categories = []
        for client in self.clients:
            result = await client.get_categories()
            categories.extend(result)
        return categories

    async def _import_for_source(
        self,
        source: str,
        categories: list[MarketplaceCategory],
    ) -> None:
        external_ids = [category.id for category in categories] + [
            sub.id
            for category in categories
            for sub in (category.subcategories or [])
        ]
        existing = await self.gateway.get_categories_by_external_ids(
            external_ids=external_ids,
            source=source,
        )
        ids_map: dict[str, UUID] = {
            cat.external_id: cat.id for cat in existing
        }
        seen: set[tuple[str, str]] = set()
        add = []
        skipped_duplicates = 0
        skipped_empty_title = 0

        for category in categories:
            if not category.title:
                skipped_empty_title += 1
                continue
            key = (category.id, source)
            if key in seen:
                skipped_duplicates += 1
                continue
            seen.add(key)
            parent_id = ids_map.get(category.id) or uuid7()
            add.append(
                ProjectCategory(
                    id=parent_id,
                    external_id=category.id,
                    source=source,
                    title=category.title,
                    parent_id=None,
                ),
            )
            for sub in category.subcategories:
                if not sub.title:
                    continue
                sub_key = (sub.id, source)
                if sub_key in seen:
                    continue
                seen.add(sub_key)
                add.append(
                    ProjectCategory(
                        id=ids_map.get(sub.id) or uuid7(),
                        external_id=sub.id,
                        source=source,
                        title=sub.title,
                        parent_id=parent_id,
                    ),
                )
        await self.gateway.upsert(add)
        logger.info(
            f"Imported {len(add)} categories for source={source} "
            f"(skipped duplicates={skipped_duplicates}, "
            f"empty titles={skipped_empty_title})",
        )


class ProjectSyncService:
    def __init__(  # noqa: PLR0917
        self,
        integrations: Sequence[MarketplaceIntegration],
        category_gateway: ProjectCategoryGateway,
        project_gateway: ProjectGateway,
        customer_gateway: CustomerGateway,
        transaction_manager: TransactionManager,
        lock_manager: DistributedLockManager,
        notification_queue: ProjectNotificationQueue,
    ):
        self.integrations = {i.source: i for i in integrations}
        self.category_gateway = category_gateway
        self.project_gateway = project_gateway
        self.customer_gateway = customer_gateway
        self.transaction_manager = transaction_manager
        self.lock_manager = lock_manager
        self.notification_queue = notification_queue

    async def sync(self, source: Marketplace) -> list[UUID]:
        integration = self.integrations.get(source)
        if integration is None:
            raise MarketplaceIntegrationNotFoundError(source)
        if integration.lock is None:
            return await self._sync_integration(integration)

        options = integration.lock

        async with self.lock_manager.try_lock(
            key=options.key,
            timeout=options.timeout,
            blocking=options.blocking,
            blocking_timeout=options.blocking_timeout,
        ) as acquired:
            if not acquired:
                logger.info(
                    f"Project sync is already running: source={source}",
                )
                return []

            return await self._sync_integration(integration)

    async def _sync_integration(
        self,
        integration: MarketplaceIntegration,
    ) -> list[UUID]:
        collector = integration.collector
        projects = await collector.collect()
        saved_ids = await self._save_projects(
            projects=projects,
            source=integration.source,
        )
        if saved_ids:
            await self.notification_queue.enqueue(saved_ids)
        return saved_ids

    def _normalize_description(self, text: str) -> str:
        # 1. Декодируем HTML entities
        text = html.unescape(text)

        # 2. <br> -> перенос строки
        text = re.sub(r"<br\s*/?>", "\n", text)

        # 3. Удаляем остальные HTML-теги
        text = re.sub(r"<[^>]+>", "", text)

        # 4. Нормализуем переносы строк
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 5. Убираем лишние пробелы
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

    async def _save_customers(
        self,
        source: Marketplace,
        projects: list[MarketplaceProject],
    ) -> dict[str, UUID]:
        now = datetime.now(UTC)
        customers = {}
        for project in projects:
            customer = project.customer
            if customer is None:
                continue
            customers.setdefault(
                customer.id,
                Customer(
                    id=uuid7(),
                    external_id=customer.id,
                    source=source,
                    username=customer.username,
                    profile_picture=customer.profile_picture,
                    user_projects_count=customer.user_projects_count,
                    user_hired_percent=customer.user_hired_percent,
                    created_at=now,
                    updated_at=now,
                ),
            )
        if not customers:
            return {}

        saved = await self.customer_gateway.bulk_upsert(
            list(customers.values()),
        )
        return {customer.external_id: customer.id for customer in saved}

    def _deduplicate_projects(
        self,
        projects: list[MarketplaceProject],
    ) -> list[MarketplaceProject]:
        result = {}
        for project in projects:
            result.setdefault(
                project.id,
                project,
            )
        return list(result.values())

    async def _save_projects(
        self,
        projects: list[MarketplaceProject],
        source: Marketplace,
    ) -> list[UUID]:
        if not projects:
            return []

        if any(project.source != source for project in projects):
            raise ValueError(f"Project source mismatch: expected={source}")

        projects = self._deduplicate_projects(projects)
        existing_projects = (
            await self.project_gateway.get_projects_by_external_ids(
                external_ids=[project.id for project in projects],
                source=source,
            )
        )
        existing_map = {
            project.external_id: project for project in existing_projects
        }

        changed_projects: list[
            tuple[MarketplaceProject, str, datetime | None]
        ] = []

        for project in projects:
            existing = existing_map.get(project.id)
            description = self._normalize_description(project.description)
            expires_at = (
                existing.expires_at if existing is not None else None
            )
            expiry_changed = project.expires_at is not None and (
                expires_at is None
                or project.expires_at > expires_at + timedelta(minutes=5)
            )
            if expiry_changed:
                expires_at = project.expires_at

            if existing is not None and (
                project.title == existing.title
                and description == existing.description
                and project.price == existing.price
                and not expiry_changed
            ):
                continue

            changed_projects.append((project, description, expires_at))

        if not changed_projects:
            return []

        category_ids = list({
            project.category_id
            for project, _, _ in changed_projects
            if project.category_id is not None
        })
        categories = (
            await self.category_gateway.get_categories_by_external_ids(
                external_ids=category_ids,
                source=source,
            )
        )
        category_map = {
            category.external_id: category.id for category in categories
        }

        missing_categories = set(category_ids) - set(category_map)
        if missing_categories:
            logger.warning(
                "Projects reference categories missing in DB: %s",
                ", ".join(sorted(missing_categories)),
            )

        customer_map = await self._save_customers(
            source=source,
            projects=[project for project, _, _ in changed_projects],
        )

        now = datetime.now(UTC)
        upserted_projects = []

        for project, description, expires_at in changed_projects:
            existing = existing_map.get(project.id)

            upserted_projects.append(
                Project(
                    id=existing.id if existing is not None else uuid7(),
                    external_id=project.id,
                    source=source,
                    title=project.title,
                    description=description,
                    price=project.price,
                    possible_price_limit=project.possible_price_limit,
                    has_exact_budget=project.has_exact_budget,
                    category_id=category_map.get(project.category_id),
                    customer_id=(
                        customer_map.get(project.customer.id)
                        if project.customer is not None
                        else None
                    ),
                    offers=project.offers,
                    created_at=(
                        existing.created_at if existing is not None else now
                    ),
                    updated_at=now,
                    expires_at=expires_at,
                ),
            )

        saved_ids = await self.project_gateway.bulk_upsert(upserted_projects)
        await self.transaction_manager.commit()
        return saved_ids


class ProjectProposalRequestService:
    def __init__(
        self,
        project_gateway: ProjectGateway,
        project_proposal_gateway: ProjectProposalGateway,
        freelancer_profile_gateway: FreelancerProfileGateway,
        project_proposal_request_gateway: ProjectProposalRequestGateway,
        subscription_checker: SubscriptionChecker,
        limit_checker: GenerationLimitChecker,
        proposal_generation_queue: ProposalGenerationQueue,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.project_gateway = project_gateway
        self.project_proposal_gateway = project_proposal_gateway
        self.freelancer_profile_gateway = freelancer_profile_gateway
        self.project_proposal_request_gateway = (
            project_proposal_request_gateway
        )
        self.subscription_checker = subscription_checker
        self.limit_checker = limit_checker
        self.proposal_generation_queue = proposal_generation_queue
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def request_generation(
        self,
        project_id: UUID,
    ) -> ProjectProposalGenerationRequestResult:
        """
        Идемпотентно регистрирует запрос на генерацию:
        если отклик уже готов, возвращает его сразу;
        если генерация уже запрошена, не ставит повторную задачу.
        """
        user_id = await self.id_provider.get_current_user_id()
        project = await self.project_gateway.get_by_id(project_id=project_id)
        if not project:
            raise ProjectNotFoundError
        freelancer_profile = await self.freelancer_profile_gateway.get(user_id)
        if freelancer_profile is None:
            raise UserFreelancerProfileNotFoundError
        proposal = await self.project_proposal_gateway.get(
            user_id=user_id,
            project_id=project_id,
        )
        if proposal:
            return ProjectProposalGenerationRequestResult(
                status=ProjectProposalGenerationRequestStatus.ALREADY_GENERATED,
                generated_text=proposal.generated_text,
            )
        can_generate = await self.limit_checker.can_generate(user_id)
        if not can_generate:
            is_pro_user = await self.subscription_checker.is_pro_user(user_id)
            limit = await self.limit_checker.get_limit(user_id)
            raise GenerationLimitExceededError(limit=limit, is_pro=is_pro_user)
        now = datetime.now(UTC)
        new_request = ProjectProposalRequest(
            user_id=user_id,
            project_id=project_id,
            status=ProjectProposalRequestStatus.PENDING,
            error=None,
            created_at=now,
            updated_at=now,
        )
        created = (
            await self.project_proposal_request_gateway.create_if_not_exists(
                new_request,
            )
        )
        await self.transaction_manager.commit()
        if created:
            await self.proposal_generation_queue.enqueue(
                user_id=user_id,
                project_id=project_id,
            )
            return ProjectProposalGenerationRequestResult(
                status=ProjectProposalGenerationRequestStatus.CREATED,
                generated_text=None,
            )
        return ProjectProposalGenerationRequestResult(
            status=ProjectProposalGenerationRequestStatus.ALREADY_PENDING,
            generated_text=None,
        )


class ProjectProposalGenerationService:
    def __init__(
        self,
        project_gateway: ProjectGateway,
        project_proposal_gateway: ProjectProposalGateway,
        project_proposal_request_gateway: ProjectProposalRequestGateway,
        freelancer_profile_gateway: FreelancerProfileGateway,
        usage_gateway: UserGenerationUsageGateway,
        limit_checker: GenerationLimitChecker,
        subscription_checker: SubscriptionChecker,
        proposal_generator: ProjectProposalGenerator,
        transaction_manager: TransactionManager,
        notify_queue: ProposalGeneratedNotificationQueue,
    ):
        self.project_gateway = project_gateway
        self.project_proposal_gateway = project_proposal_gateway
        self.project_proposal_request_gateway = (
            project_proposal_request_gateway
        )
        self.freelancer_profile_gateway = freelancer_profile_gateway
        self.usage_gateway = usage_gateway
        self.limit_checker = limit_checker
        self.subscription_checker = subscription_checker
        self.proposal_generator = proposal_generator
        self.transaction_manager = transaction_manager
        self.notify_queue = notify_queue

    async def _try_acquire_request(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> bool:
        mark_result = await self.project_proposal_request_gateway.mark_as_processing_if_pending(
            user_id=user_id,
            project_id=project_id,
        )
        await self.transaction_manager.commit()
        return mark_result

    async def _complete_request(self, user_id: UUID, project_id: UUID):
        await self.project_proposal_request_gateway.mark_as_generated(
            user_id=user_id,
            project_id=project_id,
        )
        await self.transaction_manager.commit()

    async def _fail_request(
        self,
        user_id: UUID,
        project_id: UUID,
        error_text: str,
    ):
        await self.project_proposal_request_gateway.mark_as_failed(
            user_id=user_id,
            project_id=project_id,
            error_text=error_text,
        )
        await self.transaction_manager.commit()

    def _build_project_info(self, project: Project) -> str:
        return f"Название: {project.title}\n\nЗадание: {project.description}"

    async def generate_proposal_for_user(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> ProjectProposal | None:
        if not await self._try_acquire_request(
            user_id=user_id,
            project_id=project_id,
        ):
            return None

        try:
            freelancer_profile = await self.freelancer_profile_gateway.get(
                user_id,
            )
            if freelancer_profile is None:
                raise UserFreelancerProfileNotFoundError

            project = await self.project_gateway.get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError

            project_proposal = await self.project_proposal_gateway.get(
                user_id=user_id,
                project_id=project_id,
            )
            if project_proposal:
                await self.notify_queue.enqueue_succeeded(
                    user_id=user_id,
                    project_id=project_id,
                )
                await self._complete_request(
                    user_id=user_id,
                    project_id=project_id,
                )
                return project_proposal
            project_info = self._build_project_info(project)
            result = await self.proposal_generator.generate(
                freelancer_info=freelancer_profile.about,
                project_info=project_info,
            )
            logger.debug(f"RESULT GENERATION: {result}")
            is_pro_user = await self.subscription_checker.is_pro_user(
                user_id,
            )
            can_generate = await self.limit_checker.can_generate(user_id)
            if not can_generate:
                limit = await self.limit_checker.get_limit(user_id)
                raise GenerationLimitExceededError(
                    limit=limit,
                    is_pro=is_pro_user,
                )
            usage = await self.usage_gateway.get_or_create(user_id)
            if is_pro_user:
                usage.increment_pro()
            else:
                usage.increment_free()
            project_proposal = ProjectProposal(
                project_id=project_id,
                user_id=user_id,
                generated_text=result.text,
                prompt=result.prompt,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                cost=result.cost,
                created_at=datetime.now(UTC),
            )
            await self.project_proposal_gateway.add(project_proposal)
            await self.transaction_manager.commit()
            # TODO: Что если упадет enqueue или сам таск, продумать
            await self.notify_queue.enqueue_succeeded(
                user_id=user_id,
                project_id=project_id,
            )
            await self._complete_request(
                user_id=user_id,
                project_id=project_id,
            )
        except ProjectProposalGenerationError as exc:
            logger.info(f"Project info: {project_info}")
            logger.info("Project proposal generation error")
            error_text = str(exc) or traceback.format_exc()
            await self._fail_request(
                user_id=user_id,
                project_id=project_id,
                error_text=error_text,
            )
            await self.notify_queue.enqueue_failed(user_id)
            raise
        except Exception:
            error_text = traceback.format_exc()
            await self._fail_request(
                user_id=user_id,
                project_id=project_id,
                error_text=error_text,
            )
            raise
        else:
            return project_proposal
