from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    UUID as SA_UUID,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from lansly.articles.consts import FILENAME_MAX_LENGTH
from lansly.infra.database.base import Base


class ArticleImage(Base):
    __tablename__ = "article_images"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(
        String(FILENAME_MAX_LENGTH),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"ArticleImage(id={self.id}, article_id={self.article_id}, "
            f"content_type={self.content_type})"
        )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    cover_image_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("article_images.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(nullable=True)
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )

    is_published: Mapped[bool] = mapped_column(default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    def __repr__(self) -> str:
        return f"Article=(id={self.id}, title={self.title})"

    @property
    def cover_image(self) -> dict[str, str] | None:
        if self.cover_image_id is None:
            return None
        return {
            "url": f"/media/article-images/{self.cover_image_id}",
            "filename": "",
            "content_type": "",
        }
