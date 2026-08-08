import logging

from aiogram.types import ErrorEvent

from lansly.apps.telegram_bot.messages import (
    error_callback_message,
    error_message,
)

logger = logging.getLogger(__name__)


async def global_error_handler(event: ErrorEvent):
    logger.error(
        "Unhandled exceptions",
        exc_info=event.exception,
    )

    try:
        if message := event.update.message:
            await message.answer(error_message())
        elif callback := event.update.callback_query:
            await callback.answer(
                error_callback_message(),
                show_alert=True,
            )
    except Exception:
        logger.exception("Failed to notify user")
