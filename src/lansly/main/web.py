import logging

from aiogram import Bot
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from lansly.apps.web.exception_handlers import (
    http_exception_handler,
    server_error_handler,
)
from lansly.apps.web.middlewares.not_found import NotFoundMiddleware
from lansly.apps.web.middlewares.security import SecurityHeadersMiddleware
from lansly.apps.web.routers.articles import router as articles_router
from lansly.apps.web.routers.index import router as index_router
from lansly.apps.web.routers.media import router as media_router
from lansly.apps.web.routers.robots import router as robots_router
from lansly.apps.web.routers.sitemap import router as sitemap_router
from lansly.main.config import Config, get_config
from lansly.main.di import WebProvider, create_container


def setup_middlewares(app: FastAPI) -> None:
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(NotFoundMiddleware)


def setup_routers(app: FastAPI) -> None:
    app.include_router(index_router)
    app.include_router(articles_router)
    app.include_router(media_router)
    app.include_router(robots_router)
    app.include_router(sitemap_router)


def setup_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, server_error_handler)


def create_app() -> FastAPI:
    config = get_config()
    logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO)
    bot = Bot(token=config.telegram_bot.token)
    container = create_container(
        providers=[WebProvider()],
        context={Config: config, Bot: bot},
    )
    if config.debug:
        app = FastAPI(debug=config.debug)
    else:
        app = FastAPI(
            debug=config.debug,
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
    app.mount(
        "/static",
        StaticFiles(directory=config.web.static_dir),
        name="static",
    )
    setup_middlewares(app)
    setup_routers(app)
    setup_error_handlers(app)
    setup_dishka(container, app)
    return app
