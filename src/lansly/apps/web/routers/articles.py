import logging

from http import HTTPStatus
from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates

from lansly.articles.exceptions import ArticleNotFoundError
from lansly.articles.service import ArticleService
from lansly.common.pagination import PaginationParams

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/articles/")
@inject
async def get_articles(
    request: Request,
    service: FromDishka[ArticleService],
    templates: FromDishka[Jinja2Templates],
    page: Annotated[str | None, Query()] = None,
    per_page: Annotated[str | None, Query()] = None,
):
    logger.debug(f"Pagination query params: {page}, {per_page}")
    try:
        pagination = PaginationParams(
            page=int(page) if page else 1,
            per_page=int(per_page) if per_page else 10,
        )
    except ValueError:
        pagination = PaginationParams()
    result = await service.get_articles(pagination=pagination)
    return templates.TemplateResponse(
        request=request,
        name="articles.html",
        context={"pagination": result},
    )


@router.get("/articles/{slug}/")
@inject
async def get_article(
    slug: str,
    request: Request,
    service: FromDishka[ArticleService],
    templates: FromDishka[Jinja2Templates],
):
    try:
        article = await service.get_article(slug)
    except ArticleNotFoundError:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Article not found",
        )
    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={"article": article},
    )
