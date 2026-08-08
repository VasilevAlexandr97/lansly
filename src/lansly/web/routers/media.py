from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response
from starlette.status import HTTP_404_NOT_FOUND

from lansly.articles.exceptions import ArticleImageNotFoundError
from lansly.articles.service import ArticleService

router = APIRouter()


@router.get("/media/article-images/{image_id}")
@inject
async def get_article_image(
    image_id: UUID,
    service: FromDishka[ArticleService],
):
    try:
        image = await service.get_image(image_id=image_id)
    except ArticleImageNotFoundError:
        return Response(status_code=HTTP_404_NOT_FOUND)
    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
