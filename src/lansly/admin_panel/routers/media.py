from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import JSONResponse
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)

from lansly.articles.consts import MAX_IMAGE_BYTES
from lansly.articles.dto import ArticleImageFileData
from lansly.articles.exceptions import (
    InvalidArticleImageError,
)
from lansly.articles.service import ArticleService
from lansly.auth.exceptions import AuthenticationError, ForbiddenError

router = APIRouter()


@router.post("/media/article-images/upload")
@inject
async def upload_article_image(
    file: Annotated[UploadFile, File()],
    service: FromDishka[ArticleService],
):
    try:
        image = await service.upload_image(
            ArticleImageFileData(
                filename=file.filename or "",
                content_type=file.content_type or "",
                data=await file.read(MAX_IMAGE_BYTES + 1),
            ),
        )
    except (AuthenticationError, ForbiddenError):
        return Response(status_code=HTTP_403_FORBIDDEN)
    except InvalidArticleImageError as exc:
        return JSONResponse(
            content={"error": str(exc)},
            status_code=HTTP_400_BAD_REQUEST,
        )
    return JSONResponse(
        content={"location": f"/media/article-images/{image.id}"},
    )
