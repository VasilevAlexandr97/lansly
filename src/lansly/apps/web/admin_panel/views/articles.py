import logging

from typing import Any
from uuid import UUID

from dishka import AsyncContainer
from starlette.requests import Request
from starlette_admin import ImageField, TinyMCEEditorField
from starlette_admin.contrib.sqla import ModelView
from starlette_admin.exceptions import FormValidationError

from lansly.articles.consts import MAX_IMAGE_BYTES
from lansly.articles.dto import (
    ArticleCoverImageData,
    ArticleCreateData,
    ArticleImageFileData,
    ArticleUpdateData,
)
from lansly.articles.exceptions import InvalidArticleCoverImageError
from lansly.articles.models import Article
from lansly.articles.service import ArticleService

logger = logging.getLogger(__name__)


class CoverImageField(ImageField):
    async def serialize_value(self, request, value):
        if (
            isinstance(value, dict)
            and value.get("url")
            and not value["url"].startswith(("http://", "https://"))
        ):
            value = {
                **value,
                "url": f"{request.base_url.scheme}://{request.base_url.netloc}{value['url']}",
            }
        return value


class ArticleView(ModelView):
    fields = [  # noqa: RUF012
        Article.id,
        Article.title,
        CoverImageField("cover_image"),
        Article.slug,
        Article.description,
        TinyMCEEditorField(
            "content",
            menubar=True,
            height=500,
            toolbar=(
                "undo redo | blocks | bold italic underline strikethrough | "
                "forecolor backcolor | alignleft aligncenter alignright alignjustify | "
                "bullist numlist outdent indent | blockquote | link image | "
                "table | code | removeformat"
            ),
            extra_options={
                "plugins": (
                    "advlist autolink link image lists charmap code table "
                    "preview fullscreen searchreplace wordcount"
                ),
                "block_formats": (
                    "Paragraph=p; Heading 1=h1; Heading 2=h2; Heading 3=h3; "
                    "Heading 4=h4; Heading 5=h5; Heading 6=h6"
                ),
                "link_target": "_blank",
                "branding": False,
                "images_upload_url": "/media/article-images/upload",
                "relative_urls": False,
                "remove_script_host": False,
                "convert_urls": False,
            },
        ),
        Article.meta_title,
        Article.meta_description,
        Article.is_published,
        Article.published_at,
        Article.created_at,
        Article.updated_at,
    ]
    exclude_fields_from_create = [  # noqa: RUF012
        "slug",
        "cover_image_id",
        "published_at",
        "created_at",
        "updated_at",
    ]
    exclude_fields_from_edit = [  # noqa: RUF012
        "slug",
        "cover_image_id",
        "published_at",
        "updated_at",
    ]
    fields_default_sort = [(Article.created_at, True)]

    async def _to_cover_data(
        self,
        data: dict[str, Any],
    ) -> ArticleCoverImageData:
        file, should_delete = data.get("cover_image") or (None, False)
        if file is None:
            return ArticleCoverImageData(
                file=None,
                should_delete=should_delete,
            )
        return ArticleCoverImageData(
            file=ArticleImageFileData(
                filename=file.filename or "",
                content_type=file.content_type or "",
                data=await file.read(MAX_IMAGE_BYTES + 1),
            ),
            should_delete=should_delete,
        )

    async def _to_data_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": data.get("title") or "",
            "content": data.get("content") or "",
            "description": data.get("description"),
            "meta_title": data.get("meta_title"),
            "meta_description": data.get("meta_description"),
            "is_published": bool(data.get("is_published")),
            "cover": await self._to_cover_data(data),
        }

    async def _to_create_data(self, data: dict[str, Any]) -> ArticleCreateData:
        data_fields = await self._to_data_fields(data)
        return ArticleCreateData(**data_fields)

    async def _to_edit_data(self, data: dict[str, Any]) -> ArticleUpdateData:
        data_fields = await self._to_data_fields(data)
        return ArticleUpdateData(**data_fields)

    async def create(self, request: Request, data: dict[str, Any]):
        container: AsyncContainer = request.state.dishka_container
        async with container() as req_c:
            service = await req_c.get(ArticleService)
            try:
                await self.validate(request, data)
                return await service.create_article(
                    await self._to_create_data(data),
                )
            except InvalidArticleCoverImageError as exc:
                raise FormValidationError({"cover_image": str(exc)})
            except FormValidationError:
                raise

    async def edit(self, request: Request, pk, data: dict[str, Any]):
        container: AsyncContainer = request.state.dishka_container
        async with container() as req_c:
            service = await req_c.get(ArticleService)
            try:
                await self.validate(request, data)
                return await service.update_article(
                    article_id=UUID(pk),
                    data=await self._to_edit_data(data),
                )
            except InvalidArticleCoverImageError as exc:
                raise FormValidationError({"cover_image": str(exc)})
            except FormValidationError:
                raise

    async def delete(self, request: Request, pks):
        container: AsyncContainer = request.state.dishka_container
        async with container() as req_c:
            service = await req_c.get(ArticleService)
            for pk in pks:
                await service.delete_article(UUID(pk))
        return len(pks)
