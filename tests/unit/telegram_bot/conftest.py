from collections.abc import Generator

import pytest

from aiogram import Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    make_async_container,
    provide,
)
from dishka.integrations.aiogram import setup_dishka
from fakes.preferences import FakeFollowService
from fakes.telegram_auth import FakeTelegramAuth
from fakes.telegram_bot import BotClient, FakeBot

from lansly.apps.telegram_bot.handlers.default import router as default_router
from lansly.auth.telegram_auth import TelegramAuth
from lansly.preferences.services import UserCategoryFollowService


class HandlerTestProvider(Provider):
    def __init__(
        self,
        auth: FakeTelegramAuth,
        follow_service: FakeFollowService,
    ):
        super().__init__()
        self.auth = auth
        self.follow_service = follow_service

    @provide(scope=Scope.REQUEST, provides=TelegramAuth)
    def get_auth(self) -> FakeTelegramAuth:
        return self.auth

    @provide(scope=Scope.REQUEST, provides=UserCategoryFollowService)
    def get_service(self) -> FakeFollowService:
        return self.follow_service


@pytest.fixture
def fake_auth() -> FakeTelegramAuth:
    return FakeTelegramAuth()


@pytest.fixture
def fake_follow_service() -> FakeFollowService:
    return FakeFollowService()


@pytest.fixture
def container(
    fake_auth: FakeTelegramAuth,
    fake_follow_service: FakeFollowService,
) -> AsyncContainer:
    return make_async_container(
        HandlerTestProvider(
            auth=fake_auth,
            follow_service=fake_follow_service,
        ),
    )


@pytest.fixture
def memory_storage() -> MemoryStorage:
    return MemoryStorage()


def include_routers(dp: Dispatcher):
    dp.include_router(default_router)


def detach_router(router: Router):
    for child in router.sub_routers:
        detach_router(child)

    if router._parent_router is not None:  # noqa: SLF001
        router._parent_router = None  # noqa: SLF001


def detach_routers():
    detach_router(default_router)


@pytest.fixture
def dp(
    container: AsyncContainer,
    memory_storage: MemoryStorage,
) -> Generator[Dispatcher]:
    dp = Dispatcher(storage=memory_storage)
    include_routers(dp)
    setup_dishka(container, dp)
    yield dp
    detach_routers()


@pytest.fixture
def bot_client(dp: Dispatcher) -> BotClient:
    return BotClient(dp, FakeBot())
