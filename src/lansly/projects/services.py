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
from lansly.projects.dto import (
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
    GenerationLimitChecker,
    MarketPlaceClient,
    ProjectCategoryGateway,
    ProjectGateway,
    ProposalGenerationQueue,
)
from lansly.projects.models import (
    Project,
    ProjectCategory,
    ProjectProposal,
    ProjectProposalRequest,
    ProjectProposalRequestStatus,
    ProjectSource,
)
from lansly.subscriptions.interfaces import SubscriptionChecker

logger = logging.getLogger(__name__)


class ProjectCategoryService:
    def __init__(
        self,
        gateway: ProjectCategoryGateway,
        transaction_manager: TransactionManager,
        marketplace_client: MarketPlaceClient,
    ):
        self.gateway = gateway
        self.marketplace_client = marketplace_client
        self.transaction_manager = transaction_manager

    async def import_categories(self) -> None:
        categories = await self.marketplace_client.get_categories()
        if not categories:
            return
        count_categories = sum(
            1 + len(cat.subcategories or []) for cat in categories
        )
        logger.info(f"Fetched categories from kwork: {count_categories}")
        external_ids = [category.id for category in categories] + [
            sub.id
            for category in categories
            for sub in (category.subcategories or [])
        ]
        existing = await self.gateway.get_categories_by_external_ids(
            external_ids=external_ids,
            source=ProjectSource.KWORK,
        )
        ids_map: dict[str, UUID] = {
            cat.external_id: cat.id for cat in existing
        }

        seen_keys: set[tuple[str, str]] = set()
        add_categories = []
        for category in categories:
            if not category.title:
                continue
            key = (category.id, ProjectSource.KWORK)
            if key in seen_keys:
                logger.warning(
                    f"Skip duplicate kwork category id={category.id}",
                )
                continue
            seen_keys.add(key)
            parent_id = ids_map.get(category.id) or uuid7()
            add_categories.append(
                ProjectCategory(
                    id=parent_id,
                    external_id=category.id,
                    source=ProjectSource.KWORK,
                    title=category.title,
                    parent_id=None,
                ),
            )
            for sub in category.subcategories:
                if not sub.title:
                    continue
                sub_key = (sub.id, ProjectSource.KWORK)
                if sub_key in seen_keys:
                    logger.warning(
                        f"Skip duplicate kwork subcategory id={sub.id}",
                    )
                    continue
                seen_keys.add(sub_key)
                add_categories.append(
                    ProjectCategory(
                        id=ids_map.get(sub.id) or uuid7(),
                        external_id=sub.id,
                        source=ProjectSource.KWORK,
                        title=sub.title,
                        parent_id=parent_id,
                    ),
                )
        await self.gateway.upsert(add_categories)
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
        transaction_manager: TransactionManager,
        marketplace_client: MarketPlaceClient,
    ):
        self.category_gateway = category_gateway
        self.project_gateway = project_gateway
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
        external_ids = [project.id for project in projects]
        missing_project_ids = (
            await self.project_gateway.get_missing_external_ids(
                external_ids=external_ids,
                source=ProjectSource.KWORK,
            )
        )
        cats_external_ids = [
            project.category_id
            for project in projects
            if project.category_id is not None
        ]
        categories = (
            await self.category_gateway.get_categories_by_external_ids(
                cats_external_ids,
                source=ProjectSource.KWORK,
            )
        )
        categories_map: dict[str, UUID] = {
            category.external_id: category.id for category in categories
        }
        missing_categories = {
            category_id
            for category_id in cats_external_ids
            if category_id is not None
        } - set(categories_map)
        if missing_categories:
            logger.warning(
                "Kwork projects reference categories missing in DB: %s",
                ", ".join(sorted(missing_categories)),
            )
        new_projects: list[Project] = []
        if missing_project_ids:
            seen_keys: set[tuple[str, str]] = set()
            for project in projects:
                if project.id not in missing_project_ids:
                    continue
                key = (project.id, ProjectSource.KWORK)
                if key in seen_keys:
                    logger.warning(
                        f"Skip duplicate kwork project id={project.id}",
                    )
                    continue
                seen_keys.add(key)
                new_projects.append(
                    Project(
                        id=uuid7(),
                        external_id=project.id,
                        source=ProjectSource.KWORK,
                        category_id=categories_map.get(project.category_id),
                        price=project.price,
                        possible_price_limit=project.possible_price_limit,
                        title=project.title,
                        description=self._clean_project_description(
                            project.description,
                        ),
                        offers=project.offers,
                    ),
                )
        if new_projects:
            await self.project_gateway.bulk_insert(new_projects)
            await self.transaction_manager.commit()
        return [project.id for project in new_projects]


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
