import logging

from collections.abc import Awaitable, Callable
from hashlib import md5
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis import RedisError
from redis.asyncio import Redis

from lansly.apps.telegram_bot.messages import antiflood_message

logger = logging.getLogger(__name__)


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, ttl: int = 2):
        self.redis_client = redis
        self.ttl = ttl

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id
            if isinstance(event, Message):
                chat_id = event.chat.id
                event_data = event.text
            elif isinstance(event, CallbackQuery):
                if not event.message:
                    return await handler(event, data)
                chat_id = event.message.chat.id
                event_data = event.data
            if not event_data:
                return await handler(event, data)
            hashed_event_data = md5(
                event_data.encode(),
                usedforsecurity=False,
            ).hexdigest()
            key = f"antiflood:{user_id}:{chat_id}:{hashed_event_data}"
            try:
                locked = await self.redis_client.set(
                    key,
                    "1",
                    nx=True,
                    ex=self.ttl,
                )
            except RedisError:
                logger.warning(f"Redis unavailable for antiflood key={key}")
                return await handler(event, data)
            if locked is not None:
                return await handler(event, data)
            logger.info(
                f"AntifloodMiddleware: user_id={user_id}, "
                f"chat_id={chat_id} "
                f"event_type={type(event).__name__} "
                f"event_data={event_data}",
            )
            if isinstance(event, CallbackQuery):
                await event.answer(antiflood_message())
            return None
        return await handler(event, data)
