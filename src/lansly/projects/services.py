import html
import logging
import re
import traceback

from datetime import UTC, datetime
from uuid import UUID, uuid7

from lansly.auth.interfaces import IdProvider
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.notifications.interfaces import (
    ProposalGeneratedNotificationQueue,
)
from lansly.preferences.exceptions import UserFreelancerProfileNotFoundError
from lansly.preferences.interfaces import FreelancerProfileGateway
from lansly.projects.consts import MarketPlace
from lansly.projects.dto import (
    MarketPlaceCategory,
    ProjectProposalGenerationRequestResult,
    ProjectProposalGenerationRequestStatus,
)
from lansly.projects.exceptions import (
    GenerationLimitExceededError,
    ProjectNotFoundError,
    ProjectProposalGenerationError,
)
from lansly.projects.gateways import (
    ProjectProposalGateway,
    ProjectProposalRequestGateway,
    UserGenerationUsageGateway,
)
from lansly.projects.generators import ProjectProposalGenerator
from lansly.projects.interfaces import (
    CustomerGateway,
    GenerationLimitChecker,
    MarketPlaceClient,
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
        gateway: ProjectCategoryGateway,
        transaction_manager: TransactionManager,
        marketplace_clients: list[MarketPlaceClient],
    ):
        self.gateway = gateway
        self.marketplace_clients = marketplace_clients
        self.transaction_manager = transaction_manager

    async def _get_marketplace_categories(self) -> list[MarketPlaceCategory]:
        categories = []
        for client in self.marketplace_clients:
            result = await client.get_categories()
            categories.extend(result)
        return categories

    async def _import_for_source(
        self,
        source: str,
        categories: list[MarketPlaceCategory],
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

    async def import_categories(self) -> None:
        all_categories = await self._get_marketplace_categories()
        if not all_categories:
            return

        total = sum(1 + len(c.subcategories or []) for c in all_categories)
        logger.info(
            f"Fetched {total} categories "
            f"from {len(self.marketplace_clients)} marketplaces",
        )

        by_source: dict[str, list[MarketPlaceCategory]] = {}
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


class ProjectSyncService:
    def __init__(
        self,
        category_gateway: ProjectCategoryGateway,
        project_gateway: ProjectGateway,
        customer_gateway: CustomerGateway,
        transaction_manager: TransactionManager,
        marketplace_client: MarketPlaceClient,
    ):
        self.category_gateway = category_gateway
        self.project_gateway = project_gateway
        self.customer_gateway = customer_gateway
        self.transaction_manager = transaction_manager
        self.marketplace_client = marketplace_client

    def _clean_project_description(self, text: str) -> str:
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

    async def get_and_save_new_projects(self):
        projects = await self.marketplace_client.get_projects(
            categories_ids=["all"],
        )
        if not projects:
            return []

        # 1. Фильтруем только новые проекты
        external_ids = [project.id for project in projects]
        missing_project_ids = (
            await self.project_gateway.get_missing_external_ids(
                external_ids=external_ids,
                source=ProjectSource.KWORK,
            )
        )
        if not missing_project_ids:
            return []
        new_projects = [p for p in projects if p.id in missing_project_ids]

        # 2. Категории только из новых проектов
        cats_external_ids = [
            p.category_id for p in new_projects if p.category_id
        ]
        categories = (
            await self.category_gateway.get_categories_by_external_ids(
                cats_external_ids,
                source=ProjectSource.KWORK,
            )
        )
        categories_map: dict[str, UUID] = {
            c.external_id: c.id for c in categories
        }

        missing_categories = set(cats_external_ids) - set(categories_map)
        if missing_categories:
            logger.warning(
                "Kwork projects reference categories missing in DB: %s",
                ", ".join(sorted(missing_categories)),
            )

        now = datetime.now(UTC)
        unique_customers: dict[str, Customer] = {}
        for p in new_projects:
            if p.customer and p.customer.id not in unique_customers:
                unique_customers[p.customer.id] = Customer(
                    id=uuid7(),
                    external_id=p.customer.id,
                    source=ProjectSource.KWORK,
                    username=p.customer.username,
                    profile_picture=p.customer.profile_picture,
                    user_projects_count=p.customer.user_projects_count,
                    user_hired_percent=p.customer.user_hired_percent,
                    created_at=now,
                    updated_at=now,
                )

        upserted = []
        if unique_customers:
            upserted = await self.customer_gateway.bulk_upsert(
                list(unique_customers.values()),
            )
        customer_map = {c.external_id: c.id for c in upserted}

        projects_to_add: dict[str, Project] = {}
        for p in new_projects:
            key = f"{p.id}:{ProjectSource.KWORK}"
            if key not in projects_to_add:
                customer_id = (
                    customer_map.get(p.customer.id) if p.customer else None
                )
                projects_to_add[key] = Project(
                    id=uuid7(),
                    external_id=p.id,
                    source=ProjectSource.KWORK,
                    category_id=categories_map.get(p.category_id),
                    customer_id=customer_id,
                    price=p.price,
                    possible_price_limit=p.possible_price_limit,
                    title=p.title,
                    description=self._clean_project_description(
                        p.description,
                    ),
                    offers=p.offers,
                    created_at=now,
                )
        if projects_to_add:
            await self.project_gateway.bulk_insert(
                list(projects_to_add.values()),
            )
            await self.transaction_manager.commit()
        return [project.id for project in projects_to_add.values()]


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
