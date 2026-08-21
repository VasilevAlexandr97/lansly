from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    UUID as SA_UUID,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lansly.infra.database.base import Base
from lansly.projects.consts import MarketPlace


class ProjectProposalRequestStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    GENERATED = "generated"
    FAILED = "failed"


class ProjectCategory(Base):
    __tablename__ = "project_categories"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32),
        default=MarketPlace.KWORK,
        server_default=MarketPlace.KWORK,
        nullable=False,
    )
    title: Mapped[str]
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    projects: Mapped[list["Project"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )
    follows: Mapped[list["UserCategoryFollow"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "external_id",
            "source",
            name="uq_project_categories_external_id_source",
        ),
    )

    def __repr__(self):
        return f"ProjectCategory(id={self.id}, title={self.title})"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32),
        default=MarketPlace.KWORK,
        server_default=MarketPlace.KWORK,
        nullable=False,
    )
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    price: Mapped[int]
    possible_price_limit: Mapped[int]
    title: Mapped[str]
    description: Mapped[str]
    offers: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    category: Mapped[ProjectCategory] = relationship(
        back_populates="projects",
    )
    customer: Mapped["Customer | None"] = relationship(
        back_populates="projects",
    )
    proposals: Mapped[list["ProjectProposal"]] = relationship(
        back_populates="project",
    )

    __table_args__ = (
        UniqueConstraint(
            "external_id",
            "source",
            name="uq_projects_external_id_source",
        ),
    )

    def __repr__(self):
        return f"Project(id={self.id}, title={self.title})"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32),
        default=MarketPlace.KWORK,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    # Kwork-specific
    user_projects_count: Mapped[int | None] = mapped_column(nullable=True)
    user_hired_percent: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="customer")

    __table_args__ = (
        UniqueConstraint(
            "external_id",
            "source",
            name="uq_customer_external_id_source",
        ),
    )


class ProjectProposalRequest(Base):
    __tablename__ = "project_proposal_requests"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProjectProposalRequestStatus.PENDING,
    )
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ProjectProposal(Base):
    __tablename__ = "project_proposals"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    generated_text: Mapped[str]

    prompt: Mapped[str]
    prompt_tokens: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default=sa_text("0"),
    )
    completion_tokens: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default=sa_text("0"),
    )
    total_tokens: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default=sa_text("0"),
    )
    cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=10),
        server_default=sa_text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="proposals",
        lazy="raise",
    )
    project: Mapped["Project"] = relationship(
        back_populates="proposals",
        lazy="raise",
    )


class UserGenerationUsage(Base):
    __tablename__ = "user_generation_usage"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    free_generations: Mapped[int] = mapped_column(default=0)
    pro_generations: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def increment_free(self, amount: int = 1):
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.free_generations += amount
        self._touch()

    def increment_pro(self, amount: int = 1):
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.pro_generations += amount
        self._touch()

    def reset_pro_generations(self):
        self.pro_generations = 0
        self._touch()

    def _touch(self):
        self.updated_at = datetime.now(UTC)
