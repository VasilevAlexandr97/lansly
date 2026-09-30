from typing import TypedDict

from aiogram.types import ReplyMarkupUnion

from lansly.notifications.models import (
    ChannelNotification,
    ProjectNotification,
)


class FakeProjectNotificationGateway:
    def __init__(self) -> None:
        self.rows: list[ProjectNotification] = []

    async def bulk_insert(self, rows: list[ProjectNotification]) -> None:
        self.rows.extend(rows)


class FakeChannelNotificationGateway:
    def __init__(self) -> None:
        self.rows: list[ChannelNotification] = []

    async def bulk_insert(self, rows: list[ChannelNotification]) -> None:
        self.rows.extend(rows)


class NotificationMessage(TypedDict):
    chat_id: int
    text: str
    keyboard: ReplyMarkupUnion | None


class FakeTelegramNotifier:
    def __init__(self) -> None:
        self.attempts: list[NotificationMessage] = []
        self.sent: list[NotificationMessage] = []
        self.errors: dict[int, Exception] = {}
        self.fail_next = 0

    async def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: ReplyMarkupUnion | None = None,
    ) -> None:
        message = NotificationMessage(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
        )
        self.attempts.append(message)
        if self.fail_next:
            self.fail_next -= 1
            raise RuntimeError("Telegram unavailable")
        if chat_id in self.errors:
            raise self.errors[chat_id]
        self.sent.append(message)
