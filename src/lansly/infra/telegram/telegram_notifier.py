from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import ReplyMarkupUnion


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
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
