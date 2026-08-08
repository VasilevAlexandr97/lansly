import logging

from contextlib import asynccontextmanager

from aiogram import Bot
from dishka import AsyncContainer
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin.contrib.sqla import Admin

from lansly.apps.web.admin_panel.auth import AdminPanelAuthProvider
from lansly.apps.web.admin_panel.routers.media import (
    router as upload_media_router,
)
from lansly.apps.web.admin_panel.views.articles import ArticleView
from lansly.apps.web.admin_panel.views.projects import (
    ProjectProposalView,
    ProjectView,
)
from lansly.apps.web.admin_panel.views.users import UserView
from lansly.apps.web.routers.media import router as get_media_router
from lansly.articles.models import Article
from lansly.main.config import Config, get_config
from lansly.main.di import (
    AdminPanelProvider,
    AuthProvider,
    create_container,
)
from lansly.projects.models import Project, ProjectProposal
from lansly.users.models import User

logger = logging.getLogger(__name__)


def setup_routers(app: FastAPI) -> None:
    app.include_router(get_media_router)
    app.include_router(upload_media_router)


def setup_middlewares(app: FastAPI, config: Config) -> None:
    app.add_middleware(
        SessionMiddleware,
        session_cookie="__adm_s",
        max_age=config.admin_panel.session_ttl,
        secret_key=config.admin_panel.session_secret_key,
        same_site="strict",
    )


def setup_views(admin: Admin) -> None:
    admin.add_view(UserView(User))
    admin.add_view(ProjectView(Project))
    admin.add_view(ProjectProposalView(ProjectProposal))
    admin.add_view(ArticleView(Article))


def setup_admin(engine: AsyncEngine, app: FastAPI, config: Config) -> None:
    admin = Admin(
        engine=engine,
        debug=config.debug,
        auth_provider=AdminPanelAuthProvider(),
    )
    setup_views(admin)
    admin.mount_to(app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    container: AsyncContainer = app.state.dishka_container
    engine = await container.get(AsyncEngine)
    config = await container.get(Config)
    setup_admin(engine=engine, app=app, config=config)
    logger.info("Admin panel started")
    yield
    logger.info("Stopping admin panel")
    await container.close()


def create_app() -> FastAPI:
    config = get_config()
    logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO)
    bot = Bot(token=config.telegram_bot.token)
    container = create_container(
        providers=[AdminPanelProvider(), AuthProvider(), FastapiProvider()],
        context={Config: config, Bot: bot},
    )
    if config.debug:
        app = FastAPI(debug=config.debug, lifespan=lifespan)
    else:
        app = FastAPI(
            debug=config.debug,
            lifespan=lifespan,
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
    setup_middlewares(app, config)
    setup_routers(app)
    setup_dishka(container, app)
    return app
