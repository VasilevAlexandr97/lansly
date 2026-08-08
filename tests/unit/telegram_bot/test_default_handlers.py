from uuid import uuid7

import pytest

from aiogram.enums import ChatType
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from fakes.preferences import FakeFollowService
from fakes.telegram_auth import FakeTelegramAuth
from fakes.telegram_bot import BotClient

from lansly.apps.telegram_bot.keyboards import (
    build_main_menu_kbd,
    build_start_kbd,
)
from lansly.apps.telegram_bot.messages import menu_message, start_message
from lansly.auth.telegram_auth import TelegramAuthResultDTO
from lansly.projects.models import ProjectCategory

# Start handler tests


@pytest.mark.asyncio
async def test_start_handler_new_user(
    bot_client: BotClient,
    fake_follow_service: FakeFollowService,
):
    await bot_client.send_message(text="/start")
    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == start_message()
    assert sent.reply_markup == build_start_kbd()
    assert fake_follow_service.get_followed_categories_calls == 0


@pytest.mark.parametrize(
    ("is_pro", "is_admin"),
    [(False, False), (True, False), (False, True), (True, True)],
)
@pytest.mark.asyncio
async def test_start_handler_existing_user(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
    fake_follow_service: FakeFollowService,
    is_pro: bool,
    is_admin: bool,
):
    fake_auth.result = TelegramAuthResultDTO(
        user_id=uuid7(),
        is_new=False,
        is_pro=is_pro,
        is_admin=is_admin,
    )
    await bot_client.send_message(text="/start")

    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == menu_message([])
    assert sent.reply_markup == build_main_menu_kbd(
        is_pro=is_pro,
        is_admin=is_admin,
    )
    assert fake_follow_service.get_followed_categories_calls == 1


@pytest.mark.asyncio
async def test_start_handler_clears_fsm(
    bot_client: BotClient,
    memory_storage: MemoryStorage,
):
    key = StorageKey(
        bot_id=bot_client.bot.id,
        chat_id=bot_client.chat_id,
        user_id=bot_client.user.id,
    )
    await memory_storage.set_state(key=key, state="some_state")
    await memory_storage.set_data(key=key, data={"foo": "bar"})

    await bot_client.send_message(text="/start")

    assert await memory_storage.get_state(key) is None
    assert await memory_storage.get_data(key) == {}


@pytest.mark.asyncio
async def test_start_handler_existing_user_with_categories(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
    fake_follow_service: FakeFollowService,
):
    fake_auth.result = TelegramAuthResultDTO(
        user_id=uuid7(),
        is_new=False,
        is_pro=False,
        is_admin=False,
    )
    categories = [
        ProjectCategory(id=uuid7(), external_id=1, title="Python"),
        ProjectCategory(id=uuid7(), external_id=2, title="Backend"),
    ]
    fake_follow_service.categories = categories
    await bot_client.send_message(text="/start")

    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == menu_message(categories)
    assert fake_follow_service.get_followed_categories_calls == 1


@pytest.mark.asyncio
async def test_start_handler_ignores_message_without_from_user(
    bot_client: BotClient,
):
    await bot_client.send_message(text="/start", with_user=False)
    assert bot_client.bot.sent_methods == []


# Routers tests


@pytest.mark.asyncio
async def test_router_routes_start_in_private_chat(bot_client: BotClient):
    await bot_client.send_message(text="/start", chat_type=ChatType.PRIVATE)
    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == start_message()
    assert sent.reply_markup == build_start_kbd()


@pytest.mark.asyncio
async def test_router_ignores_other_text(bot_client: BotClient):
    await bot_client.send_message(text="hello", chat_type=ChatType.PRIVATE)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_other_command(bot_client: BotClient):
    await bot_client.send_message(text="/unknown", chat_type=ChatType.PRIVATE)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_group_chat(bot_client: BotClient):
    await bot_client.send_message(text="/start", chat_type=ChatType.GROUP)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_channel_chat(bot_client: BotClient):
    await bot_client.send_message(text="/start", chat_type=ChatType.CHANNEL)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_super_group_chat(bot_client: BotClient):
    await bot_client.send_message(text="/start", chat_type=ChatType.SUPERGROUP)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_sender_chat(bot_client: BotClient):
    await bot_client.send_message(text="/start", chat_type=ChatType.SENDER)
    assert bot_client.bot.sent_methods == []
