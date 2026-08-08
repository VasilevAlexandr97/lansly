import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from dishka.integrations.aiogram import AiogramProvider, setup_dishka
from redis.asyncio.client import Redis

from lansly.apps.telegram_bot.handlers.default import router as default_router
from lansly.apps.telegram_bot.handlers.errors import global_error_handler
from lansly.apps.telegram_bot.handlers.preferences import (
    router as preferences_router,
)
from lansly.apps.telegram_bot.handlers.projects import (
    router as projects_router,
)
from lansly.apps.telegram_bot.handlers.subscriptions import (
    router as subscriptions_router,
)
from lansly.apps.telegram_bot.middlewares.antiflood import AntiFloodMiddleware
from lansly.main.config import Config, config
from lansly.main.di import TelegramBotProvider, create_container

bot = Bot(
    token=config.telegram_bot.token,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML,
        link_preview_is_disabled=True,
    ),
)

container = create_container(
    providers=[AiogramProvider(), TelegramBotProvider()],
    context={Config: config, Bot: bot},
)


def setup_middlewares(dp: Dispatcher, redis: Redis):
    antiflood_middleware = AntiFloodMiddleware(redis)
    dp.message.middleware(antiflood_middleware)
    dp.callback_query.middleware(antiflood_middleware)


def setup_handlers(dp: Dispatcher):
    dp.include_router(default_router)
    dp.include_router(preferences_router)
    dp.include_router(projects_router)
    dp.include_router(subscriptions_router)
    dp.errors.register(global_error_handler)


async def get_dispatcher() -> Dispatcher:
    logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO)
    redis = await container.get(Redis)
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)
    setup_middlewares(dp, redis)
    setup_handlers(dp)
    setup_dishka(container, dp)
    return dp


def run_polling():
    dp = asyncio.run(get_dispatcher())
    dp.run_polling(bot)
