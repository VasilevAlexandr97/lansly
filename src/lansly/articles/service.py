import re

from datetime import UTC, datetime
from uuid import UUID, uuid7

from slugify import slugify

from lansly.articles.dto import (
    ArticleCreateData,
    ArticleImageFileData,
    ArticleUpdateData,
)
from lansly.articles.exceptions import (
    ArticleImageNotFoundError,
    ArticleNotFoundError,
    InvalidArticleCoverImageError,
    InvalidArticleImageError,
)
from lansly.articles.interfaces import ArticleGateway, ArticleImageGateway
from lansly.articles.models import Article, ArticleImage
from lansly.articles.validators import article_image_validator
from lansly.auth.exceptions import ForbiddenError
from lansly.auth.interfaces import IdProvider
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.common.pagination import PaginationParams, PaginationResponse


class ArticleService:
    IMAGE_URL_RE = re.compile(r"/media/article-images/([0-9a-fA-F-]{36})")

    def __init__(
        self,
        article_gateway: ArticleGateway,
        image_gateway: ArticleImageGateway,
        transaction_manager: TransactionManager,
        id_provider: IdProvider,
    ):
        self.article_gateway = article_gateway
        self.image_gateway = image_gateway
        self.transaction_manager = transaction_manager
        self.id_provider = id_provider

    async def _require_admin(self) -> None:
        user = await self.id_provider.get_current_user()
        if not user.is_admin:
            raise ForbiddenError("Admin access required")

    def _extract_image_ids(self, content: str) -> list[UUID]:
        ids = []
        for match in self.IMAGE_URL_RE.findall(content):
            try:
                ids.append(UUID(match))
            except ValueError:
                continue
        return list(dict.fromkeys(ids))

    async def _set_cover(
        self,
        article: Article,
        file: ArticleImageFileData,
        now: datetime,
    ) -> None:
        try:
            article_image_validator(file)
        except InvalidArticleImageError as exc:
            raise InvalidArticleCoverImageError(exc)
        image = ArticleImage(
            id=uuid7(),
            article_id=article.id,
            filename=file.filename or "cover",
            content_type=file.content_type,
            size_bytes=len(file.data),
            data=file.data,
            created_at=now,
        )
        await self.image_gateway.add(image)
        article.cover_image_id = image.id

    async def _make_unique_slug(self, title: str) -> str:
        base = slugify(title) or "article"
        candidate = base
        suffix = 2
        while await self.article_gateway.get_by_slug(candidate) is not None:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    async def create_article(self, data: ArticleCreateData) -> Article:
        await self._require_admin()
        now = datetime.now(UTC)
        article = Article(
            id=uuid7(),
            title=data.title,
            content=data.content,
            description=data.description,
            meta_title=data.meta_title,
            meta_description=data.meta_description,
            is_published=data.is_published,
            published_at=now if data.is_published else None,
            created_at=now,
            updated_at=now,
        )
        article.slug = await self._make_unique_slug(article.title)
        await self.article_gateway.add(article)
        if data.cover.file is not None:
            await self._set_cover(article, data.cover.file, now)
        await self.image_gateway.sync_images(
            article_id=article.id,
            referenced_ids=self._extract_image_ids(article.content),
            keep_cover_id=article.cover_image_id,
        )
        await self.transaction_manager.commit()
        return article

    async def update_article(
        self,
        article_id: UUID,
        data: ArticleUpdateData,
    ) -> Article:
        await self._require_admin()
        article = await self.article_gateway.get_by_id(article_id)
        if article is None:
            raise ArticleNotFoundError(
                f"Article with id={article_id} not found",
            )
        now = datetime.now(UTC)
        article.title = data.title
        article.content = data.content
        article.description = data.description
        article.meta_title = data.meta_title
        article.meta_description = data.meta_description
        article.is_published = data.is_published
        if article.is_published and article.published_at is None:
            article.published_at = now
        article.updated_at = now

        if data.cover.file is not None:
            await self._set_cover(article, data.cover.file, now)
        elif data.cover.should_delete:
            article.cover_image_id = None
        await self.image_gateway.sync_images(
            article_id=article.id,
            referenced_ids=self._extract_image_ids(article.content),
            keep_cover_id=article.cover_image_id,
        )
        await self.transaction_manager.commit()
        return article

    async def delete_article(self, article_id: UUID) -> None:
        await self._require_admin()
        await self.image_gateway.delete_by_article(article_id)
        await self.article_gateway.delete(article_id)
        await self.transaction_manager.commit()

    async def get_article(self, slug: str) -> Article:
        article = await self.article_gateway.get_published_by_slug(slug)
        if article is None:
            raise ArticleNotFoundError(
                f"Article with slug={slug} not found error",
            )
        return article

    async def get_articles(
        self,
        pagination: PaginationParams,
    ) -> PaginationResponse[Article]:
        total = await self.article_gateway.get_count_published()
        page = pagination.page
        per_page = pagination.per_page
        if total > 0:
            total_pages = (total + per_page - 1) // per_page
            page = min(page, total_pages)
        offset = (page - 1) * per_page
        articles = await self.article_gateway.get_published(
            limit=pagination.per_page,
            offset=offset,
        )
        return PaginationResponse(
            items=articles,
            total=total,
            page=page,
            per_page=per_page,
        )

    async def upload_image(self, file: ArticleImageFileData) -> ArticleImage:
        await self._require_admin()
        article_image_validator(file)
        image = ArticleImage(
            id=uuid7(),
            article_id=None,
            filename=file.filename or "image",
            content_type=file.content_type,
            size_bytes=len(file.data),
            data=file.data,
            created_at=datetime.now(UTC),
        )
        await self.image_gateway.add(image)
        await self.transaction_manager.commit()
        return image

    async def get_image(self, image_id: UUID) -> ArticleImage:
        image = await self.image_gateway.get_by_id(image_id)
        if image is None:
            raise ArticleImageNotFoundError(
                f"Article image with id={image_id} not found",
            )
        return image
