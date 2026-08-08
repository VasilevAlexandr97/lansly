from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_404_NOT_FOUND


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    if exc.status_code == HTTP_404_NOT_FOUND:
        templates = await request.state.dishka_container.get(
            Jinja2Templates,
        )
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            status_code=HTTP_404_NOT_FOUND,
        )
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
    )


async def server_error_handler(
    request: Request,
    _exc: Exception,
):
    templates = await request.state.dishka_container.get(Jinja2Templates)
    return templates.TemplateResponse(
        request=request,
        name="500.html",
        status_code=500,
    )
