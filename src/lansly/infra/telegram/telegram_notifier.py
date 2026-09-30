from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ReplyMarkupUnion

from lansly.notifications.exceptions import RecipientUnavailableError


class TelegramNotifier:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: ReplyMarkupUnion | None = None,
        parse_mode: str = ParseMode.HTML,
        disable_web_page_preview: bool = True,
    ):
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            unavailable = exc.message.lower() in {
                "forbidden: bot was blocked by the user",
                "forbidden: user is deactivated",
                "bad request: chat not found",
                "bad request: user is deactivated",
                "bad request: bot_blocked",
            }
            if unavailable:
                raise RecipientUnavailableError(str(exc)) from exc
            raise
