from dataclasses import dataclass


@dataclass(frozen=True)
class ArticleImageFileData:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ArticleCoverImageData:
    file: ArticleImageFileData | None
    should_delete: bool = False


@dataclass(frozen=True)
class ArticleCreateData:
    title: str
    content: str
    description: str | None
    meta_title: str | None
    meta_description: str | None
    is_published: bool
    cover: ArticleCoverImageData


@dataclass(frozen=True)
class ArticleUpdateData:
    title: str
    content: str
    description: str | None
    meta_title: str | None
    meta_description: str | None
    is_published: bool
    cover: ArticleCoverImageData
