from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_404_NOT_FOUND


class NotFoundMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        if response.status_code == HTTP_404_NOT_FOUND:
            templates = await request.state.dishka_container.get(
                Jinja2Templates,
            )
            return templates.TemplateResponse(
                request=request,
                name="404.html",
                status_code=HTTP_404_NOT_FOUND,
            )
        return response
