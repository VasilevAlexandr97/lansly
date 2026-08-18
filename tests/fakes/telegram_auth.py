from uuid import uuid7

from lansly.auth.telegram_auth import TelegramAuthResultDTO


class FakeTelegramAuth:
    def __init__(self, is_new: bool = True) -> None:
        self.result = TelegramAuthResultDTO(
            user_id=uuid7(),
            is_new=is_new,
            is_pro=False,
            is_admin=False,
        )
        self.source: str | None = None

    async def auth(self, source: str | None = None) -> TelegramAuthResultDTO:
        self.source = source
        return self.result
