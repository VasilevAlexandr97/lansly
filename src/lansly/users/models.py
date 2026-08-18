from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    UUID as SA_UUID,
    BigInteger,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lansly.infra.database.base import Base
from lansly.users.consts import SOURCE_MAX_LENGTH, USERNAME_MAX_LENGTH


class Role(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
    )
    username: Mapped[str | None] = mapped_column(
        String(USERNAME_MAX_LENGTH),
        unique=True,
        nullable=True,
    )
    source: Mapped[str | None] = mapped_column(
        String(SOURCE_MAX_LENGTH),
        nullable=True,
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    proposals: Mapped[list["ProjectProposal"]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            "UserModel("
            f"id={self.id}, "
            f"telegram_id={self.telegram_id}, "
            f"username={self.username}, "
            f"source={self.source}, "
            f"created_at={self.created_at}, "
            f"updated_at={self.updated_at}"
            ")"
        )


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(default=Role.USER)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            "UserRole("
            f"id={self.id}, "
            f"name={self.name}, "
            f"created_at={self.created_at}, "
            f"updated_at={self.updated_at}"
            ")"
        )
