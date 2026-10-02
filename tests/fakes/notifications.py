from typing import TypedDict
from uuid import UUID

from aiogram.types import ReplyMarkupUnion

from lansly.notifications.models import (
    ChannelNotification,
    ProjectNotification,
)


class FakeProjectNotificationQueue:
    def __init__(self) -> None:
        self.enqueued: list[list[UUID]] = []

    async def enqueue(self, project_ids: list[UUID]) -> None:
        self.enqueued.append(list(project_ids))


class FakeProjectNotificationGateway:
    def __init__(self) -> None:
        self.rows: list[ProjectNotification] = []

    async def bulk_upsert(self, rows: list[ProjectNotification]) -> None:
        for row in rows:
            self.rows = [
                saved
                for saved in self.rows
                if (saved.project_id, saved.user_id)
                != (row.project_id, row.user_id)
            ]
            self.rows.append(row)

    async def get(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> ProjectNotification | None:
        return next(
            (
                row
                for row in self.rows
                if row.project_id == project_id and row.user_id == user_id
            ),
            None,
        )


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
