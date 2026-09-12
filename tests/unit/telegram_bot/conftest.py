# ruff: noqa: SLF001
import pytest
import pytest_asyncio

from aiogram import Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.aiogram import setup_dishka
from fakes.factories import category
from fakes.infra import FakeTransactionManager
from fakes.preferences import MonitoringFollowService
from fakes.projects import FakeProjectCategoryGateway
from fakes.telegram_auth import FakeTelegramAuth
from fakes.telegram_bot import BotClient, FakeBot

from lansly.apps.telegram_bot.handlers import (
    category_settings,
    default,
    onboarding,
)
from lansly.auth.telegram_auth import TelegramAuth
from lansly.common.dto import CurrentUser
from lansly.preferences.services import UserCategoryFollowService
from lansly.projects.consts import Marketplace
from lansly.projects.services import ProjectCategoryService


class HandlerTestProvider(Provider):
    def __init__(self, auth, follow, categories):
        super().__init__()
        self.auth, self.follow, self.categories = auth, follow, categories

    @provide(scope=Scope.REQUEST, provides=TelegramAuth)
    async def get_auth(self) -> FakeTelegramAuth:
        return self.auth

    @provide(scope=Scope.REQUEST, provides=UserCategoryFollowService)
    async def get_follow(self) -> MonitoringFollowService:
        return self.follow

    @provide(scope=Scope.REQUEST)
    async def get_categories(self) -> ProjectCategoryService:
        return self.categories

    @provide(scope=Scope.REQUEST)
    async def get_user(self) -> CurrentUser:
        result = self.auth.result
        return CurrentUser(
            id=result.user_id,
            is_pro=result.is_pro,
            is_admin=result.is_admin,
        )


@pytest.fixture
def fake_auth():
    return FakeTelegramAuth()


@pytest.fixture
def fake_follow_service():
    return MonitoringFollowService()


@pytest.fixture
def category_service(fake_follow_service):
    cats = []
    for source in Marketplace:
        root = category(source=source)
        child = category(
            source=source,
            parent_id=root.id,
            external_id="logo",
            title="Лого",
        )
        cats.extend([root, child])
        fake_follow_service.directions[source] = [root]
        fake_follow_service.categories[root.id] = [child]
    return ProjectCategoryService(
        [],
        FakeProjectCategoryGateway(cats),
        FakeTransactionManager(),
    )


@pytest_asyncio.fixture
async def container(fake_auth, fake_follow_service, category_service):
    container = make_async_container(
        HandlerTestProvider(fake_auth, fake_follow_service, category_service),
    )
    yield container
    await container.close()


@pytest.fixture
def memory_storage():
    return MemoryStorage()


def isolated_router(source):
    # Новый Router сохраняет регистрацию, не меняя роутеры приложения.
    target = Router()
    for name, observer in source.observers.items():
        target.observers[name].handlers.extend(observer.handlers)
        for filter_ in observer._handler.filters or []:
            target.observers[name].filter(filter_.callback)
    return target


@pytest_asyncio.fixture
async def dp(container, memory_storage):
    dispatcher = Dispatcher(storage=memory_storage)
    for module in (default, onboarding, category_settings):
        dispatcher.include_router(isolated_router(module.router))
    setup_dishka(container, dispatcher)
    yield dispatcher
    await dispatcher.fsm.close()


@pytest.fixture
def bot_client(dp):
    return BotClient(dp, FakeBot())


@pytest.fixture
def state(bot_client):
    return bot_client.dp.fsm.get_context(
        bot=bot_client.bot,
        chat_id=bot_client.chat_id,
        user_id=bot_client.user.id,
    )
