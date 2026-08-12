from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from lansly.projects.interfaces import (
    ProjectCategoryGateway,
    ProjectGateway,
    UserGenerationUsageGateway,
)
from lansly.projects.models import (
    Project,
    ProjectCategory,
    ProjectProposal,
    ProjectProposalRequest,
    ProjectProposalRequestStatus,
    UserGenerationUsage,
)


class SAProjectCategoryGateway(ProjectCategoryGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, categories: list[ProjectCategory]):
        values_data = [
            {
                "id": cat.id,
                "external_id": cat.external_id,
                "source": cat.source,
                "title": cat.title,
                "parent_id": cat.parent_id,
            }
            for cat in categories
        ]
        stmt = pg_insert(ProjectCategory).values(values_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_id", "source"],
            set_={
                "title": stmt.excluded.title,
                "parent_id": stmt.excluded.parent_id,
            },
        )
        await self.session.execute(stmt)

    async def get_categories_by_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> list[ProjectCategory]:
        stmt = select(ProjectCategory).where(
            ProjectCategory.external_id.in_(external_ids),
            ProjectCategory.source == source,
        )
        return list(await self.session.scalars(stmt))

    async def get_root_categories(
        self,
        source: str | None = None,
    ) -> list[ProjectCategory]:
        stmt = select(ProjectCategory).where(
            ProjectCategory.parent_id.is_(None),
        )
        if source is not None:
            stmt = stmt.where(ProjectCategory.source == source)
        result = await self.session.scalars(stmt)
        return list(result.all())


class SAProjectGateway(ProjectGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_insert(self, projects: list[Project]) -> None:
        if not projects:
            return
        values = [
            {
                "id": project.id,
                "external_id": project.external_id,
                "source": project.source,
                "title": project.title,
                "category_id": project.category_id,
                "price": project.price,
                "possible_price_limit": project.possible_price_limit,
                "description": project.description,
                "offers": project.offers,
            }
            for project in projects
        ]
        stmt = (
            pg_insert(Project)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=["external_id", "source"],
            )
        )
        await self.session.execute(stmt)

    async def get_missing_external_ids(
        self,
        external_ids: list[str],
        source: str,
    ) -> set[str]:
        stmt = select(Project.external_id).where(
            Project.external_id.in_(external_ids),
            Project.source == source,
        )
        existing_ids = await self.session.scalars(stmt)
        return set(external_ids) - set(existing_ids)

    async def get_projects_by_ids(
        self,
        project_ids: list[UUID],
        with_category: bool = False,
    ) -> list[Project]:
        if not project_ids:
            return []
        stmt = select(Project).where(Project.id.in_(project_ids))
        if with_category:
            stmt = stmt.options(selectinload(Project.category))
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_by_id(self, project_id: UUID) -> Project | None:
        stmt = select(Project).where(Project.id == project_id)
        return await self.session.scalar(stmt)


class ProjectProposalRequestGateway:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_if_not_exists(
        self,
        request: ProjectProposalRequest,
    ) -> bool:
        stmt = (
            pg_insert(ProjectProposalRequest)
            .values(
                user_id=request.user_id,
                project_id=request.project_id,
                status=request.status,
                error=request.error,
                created_at=request.created_at,
                updated_at=request.updated_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ProjectProposalRequest.user_id,
                    ProjectProposalRequest.project_id,
                ],
            )
            .returning(
                ProjectProposalRequest.user_id,
            )
        )
        result = await self.session.scalar(stmt)
        return result is not None

    async def mark_as_processing_if_pending(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> bool:
        stmt = (
            update(ProjectProposalRequest)
            .where(
                ProjectProposalRequest.user_id == user_id,
                ProjectProposalRequest.project_id == project_id,
                ProjectProposalRequest.status
                == ProjectProposalRequestStatus.PENDING,
            )
            .values(
                status=ProjectProposalRequestStatus.PROCESSING,
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def mark_as_generated(
        self,
        user_id: UUID,
        project_id: UUID,
    ):
        stmt = (
            update(ProjectProposalRequest)
            .where(
                ProjectProposalRequest.user_id == user_id,
                ProjectProposalRequest.project_id == project_id,
            )
            .values(
                status=ProjectProposalRequestStatus.GENERATED,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)

    async def mark_as_failed(
        self,
        user_id: UUID,
        project_id: UUID,
        error_text: str,
    ):
        stmt = (
            update(ProjectProposalRequest)
            .where(
                ProjectProposalRequest.user_id == user_id,
                ProjectProposalRequest.project_id == project_id,
            )
            .values(
                status=ProjectProposalRequestStatus.FAILED,
                error=error_text,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)


class ProjectProposalGateway:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, project_proposal: ProjectProposal):
        self.session.add(project_proposal)
        await self.session.flush()

    async def get(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> ProjectProposal | None:
        stmt = select(ProjectProposal).where(
            and_(
                ProjectProposal.user_id == user_id,
                ProjectProposal.project_id == project_id,
            ),
        )
        return await self.session.scalar(stmt)

    async def get_with_user(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> ProjectProposal | None:
        stmt = (
            select(ProjectProposal)
            .options(joinedload(ProjectProposal.user))
            .where(
                and_(
                    ProjectProposal.user_id == user_id,
                    ProjectProposal.project_id == project_id,
                ),
            )
        )
        return await self.session.scalar(stmt)


class SAUserGenerationUsageGateway(UserGenerationUsageGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    # async def add(self, usage: UserGenerationUsage):
    #     self.session.add(usage)
    #     await self.session.flush()

    # async def get(self, user_id: UUID) -> UserGenerationUsage | None:
    #     stmt = select(UserGenerationUsage).where(
    #         UserGenerationUsage.user_id == user_id,
    #     )
    #     return await self.session.scalar(stmt)

    async def get_or_create(self, user_id: UUID) -> UserGenerationUsage:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(UserGenerationUsage)
            .values(
                user_id=user_id,
                free_generations=0,
                pro_generations=0,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[UserGenerationUsage.user_id],
            )
            .returning(UserGenerationUsage)
        )
        result = await self.session.execute(stmt)
        gen_usage = result.scalar_one_or_none()
        if gen_usage is not None:
            return gen_usage
        stmt = select(UserGenerationUsage).where(
            UserGenerationUsage.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
