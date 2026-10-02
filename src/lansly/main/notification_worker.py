import logging

from aiogram import Bot
from dishka.integrations.taskiq import setup_dishka
from taskiq import TaskiqEvents, TaskiqState

from lansly.infra.taskiq.broker import notification_broker
from lansly.main.config import Config, get_config
from lansly.main.di import WorkerProvider, create_container

logging.basicConfig(level=logging.INFO)

config = get_config()
bot = Bot(token=config.telegram_bot.token)
container = create_container(
    providers=[WorkerProvider()],
    context={Config: config, Bot: bot},
)

setup_dishka(container, notification_broker)


@notification_broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(_state: TaskiqState) -> None:
    try:
        await container.close()
    finally:
        await bot.session.close()
