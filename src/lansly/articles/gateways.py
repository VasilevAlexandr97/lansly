from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from lansly.articles.interfaces import ArticleGateway, ArticleImageGateway
from lansly.articles.models import Article, ArticleImage


class SAArticleImageGateway(ArticleImageGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, image: ArticleImage):
        self.session.add(image)
        await self.session.flush()

    async def delete_by_article(self, article_id: UUID) -> None:
        stmt = delete(ArticleImage).where(
            ArticleImage.article_id == article_id,
        )
        await self.session.execute(stmt)

    async def sync_images(
        self,
        article_id: UUID,
        referenced_ids: list[UUID],
        keep_cover_id: UUID | None,
    ) -> None:
        stmt = (
            update(ArticleImage)
            .where(
                ArticleImage.id.in_(referenced_ids),
                or_(
                    ArticleImage.article_id.is_(None),
                    ArticleImage.article_id == article_id,
                ),
            )
            .values(article_id=article_id)
        )
        await self.session.execute(stmt)

        delete_stmt = delete(ArticleImage).where(
            ArticleImage.article_id == article_id,
            ArticleImage.id.not_in(referenced_ids),
        )
        if keep_cover_id is not None:
            delete_stmt = delete_stmt.where(ArticleImage.id != keep_cover_id)
        await self.session.execute(delete_stmt)

    async def get_by_id(self, image_id: UUID) -> ArticleImage | None:
        stmt = select(ArticleImage).where(ArticleImage.id == image_id)
        return await self.session.scalar(stmt)


class SAArticleGateway(ArticleGateway):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, article: Article) -> None:
        self.session.add(article)
        await self.session.flush()

    async def delete(self, article_id: UUID) -> None:
        stmt = delete(Article).where(Article.id == article_id)
        await self.session.execute(stmt)

    async def get_by_id(self, article_id: UUID) -> Article | None:
        stmt = select(Article).where(Article.id == article_id)
        return await self.session.scalar(stmt)

    async def get_by_slug(self, slug: str) -> Article | None:
        stmt = select(Article).where(Article.slug == slug)
        return await self.session.scalar(stmt)

    async def get_published_by_slug(self, slug: str) -> Article | None:
        stmt = select(Article).where(
            Article.slug == slug,
            Article.is_published.is_(True),
            Article.published_at.is_not(None),
        )
        return await self.session.scalar(stmt)

    async def get_published(self, limit: int, offset: int) -> list[Article]:
        stmt = (
            select(Article)
            .where(
                Article.is_published.is_(True),
                Article.published_at.is_not(None),
            )
            .order_by(Article.published_at.desc(), Article.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(await self.session.scalars(stmt))

    async def get_published_all(self) -> list[Article]:
        stmt = (
            select(Article)
            .where(
                Article.is_published.is_(True),
                Article.published_at.is_not(None),
            )
            .order_by(Article.published_at.desc(), Article.created_at.desc())
        )
        return list(await self.session.scalars(stmt))

    async def get_count_published(self) -> int:
        stmt = select(count(Article.id)).where(
            Article.is_published.is_(True),
            Article.published_at.is_not(None),
        )
        return (await self.session.scalar(stmt)) or 0
