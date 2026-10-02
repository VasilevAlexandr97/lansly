import logging

from aiogram import Bot
from dishka.integrations.taskiq import setup_dishka
from taskiq import TaskiqEvents, TaskiqState

from lansly.infra.taskiq.broker import broker, notification_broker, scheduler
from lansly.main.config import Config, get_config
from lansly.main.di import (
    WorkerProvider,
    create_container,
)

config = get_config()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.telegram_bot.token)
container = create_container(
    providers=[WorkerProvider()],
    context={Config: config, Bot: bot},
)

setup_dishka(container, broker)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def start_notification_queue(_state: TaskiqState) -> None:
    await notification_broker.startup()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def stop_notification_queue(_state: TaskiqState) -> None:
    await notification_broker.shutdown()


logger.debug(scheduler)
