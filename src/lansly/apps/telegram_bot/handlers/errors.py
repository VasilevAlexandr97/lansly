import logging

from aiogram import Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import ExceptionMessageFilter, ExceptionTypeFilter
from aiogram.types import ErrorEvent

from lansly.apps.telegram_bot.messages import (
    error_callback_message,
    error_message,
)

router = Router()
logger = logging.getLogger(__name__)


@router.error(
    ExceptionTypeFilter(TelegramForbiddenError),
    ExceptionMessageFilter(
        r"^Telegram server says - Forbidden: bot was blocked by the user$",
    ),
)
async def bot_blocked_error_handler(event: ErrorEvent) -> None:
    logger.info(
        "User blocked the bot; update_id=%s",
        event.update.update_id,
    )


@router.error()
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
