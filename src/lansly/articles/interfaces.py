from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from lansly.articles.models import Article, ArticleImage


class ArticleImageGateway(Protocol):
    @abstractmethod
    async def add(self, image: ArticleImage):
        raise NotImplementedError

    @abstractmethod
    async def delete_by_article(self, article_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def sync_images(
        self,
        article_id: UUID,
        referenced_ids: list[UUID],
        keep_cover_id: UUID | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, image_id: UUID) -> ArticleImage | None:
        raise NotImplementedError


class ArticleGateway(Protocol):
    @abstractmethod
    async def add(self, article: Article) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, article_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, article_id: UUID) -> Article | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Article | None:
        raise NotImplementedError

    @abstractmethod
    async def get_published_by_slug(self, slug: str) -> Article | None:
        raise NotImplementedError

    @abstractmethod
    async def get_published(self, limit: int, offset: int) -> list[Article]:
        raise NotImplementedError

    @abstractmethod
    async def get_published_all(self) -> list[Article]:
        raise NotImplementedError

    @abstractmethod
    async def get_count_published(self) -> int:
        raise NotImplementedError
