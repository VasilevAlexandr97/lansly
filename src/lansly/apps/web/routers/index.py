from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates

router = APIRouter()


@router.get("/")
@inject
async def index(request: Request, templates: FromDishka[Jinja2Templates]):
    return templates.TemplateResponse(request=request, name="index.html")
