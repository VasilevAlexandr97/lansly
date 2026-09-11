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
    build_onboarding_marketplaces_kbd,
)
from lansly.apps.telegram_bot.messages import (
    menu_message,
    onboarding_start_message,
)
from lansly.apps.telegram_bot.states import OnboardingState
from lansly.auth.telegram_auth import TelegramAuthResultDTO
from lansly.preferences.dto import SourceCategoryFollowCountDTO
from lansly.projects.consts import Marketplace

# Start handler tests


@pytest.mark.asyncio
async def test_start_handler_new_user(
    bot_client: BotClient,
    fake_follow_service: FakeFollowService,
):
    # Проверяет отправку новому пользователю приветствия и клавиатуры выбора
    # площадки без запроса счётчиков подписок.
    await bot_client.send_message(text="/start")
    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == onboarding_start_message()
    assert sent.reply_markup == build_onboarding_marketplaces_kbd()
    assert fake_follow_service.follow_counts_calls == 0


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
    # Проверяет отправку главного меню существующему пользователю с кнопками
    # для его статуса PRO и роли администратора.
    fake_auth.result = TelegramAuthResultDTO(
        user_id=uuid7(),
        is_new=False,
        is_pro=is_pro,
        is_admin=is_admin,
    )
    await bot_client.send_message(text="/start")

    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == menu_message(fake_follow_service.follow_counts)
    assert sent.reply_markup == build_main_menu_kbd(
        is_pro=is_pro,
        is_admin=is_admin,
    )
    assert fake_follow_service.follow_counts_calls == 1


@pytest.mark.asyncio
async def test_start_handler_resets_fsm_before_onboarding(
    bot_client: BotClient,
    memory_storage: MemoryStorage,
):
    # Проверяет замену прежнего состояния FSM на выбор площадки и очистку
    # данных при /start нового пользователя.
    key = StorageKey(
        bot_id=bot_client.bot.id,
        chat_id=bot_client.chat_id,
        user_id=bot_client.user.id,
    )
    await memory_storage.set_state(key=key, state="some_state")
    await memory_storage.set_data(key=key, data={"foo": "bar"})

    await bot_client.send_message(text="/start")

    assert (
        await memory_storage.get_state(key)
        == OnboardingState.select_marketplace.state
    )
    assert await memory_storage.get_data(key) == {}


@pytest.mark.asyncio
async def test_start_handler_existing_user_with_follow_counts(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
    fake_follow_service: FakeFollowService,
):
    # Проверяет использование актуальных счётчиков подписок обеих площадок в
    # меню существующего пользователя по /start.
    fake_auth.result = TelegramAuthResultDTO(
        user_id=uuid7(),
        is_new=False,
        is_pro=False,
        is_admin=False,
    )
    follow_counts = [
        SourceCategoryFollowCountDTO(
            source=Marketplace.KWORK,
            followed_count=12,
        ),
        SourceCategoryFollowCountDTO(
            source=Marketplace.FL,
            followed_count=26,
        ),
    ]
    fake_follow_service.follow_counts = follow_counts
    await bot_client.send_message(text="/start")

    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == menu_message(follow_counts)
    assert fake_follow_service.follow_counts_calls == 1


@pytest.mark.asyncio
async def test_start_handler_ignores_message_without_from_user(
    bot_client: BotClient,
):
    # Проверяет, что /start без данных отправителя не вызывает обращений к
    # Telegram API.
    await bot_client.send_message(text="/start", with_user=False)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_start_handler_deep_link_source(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
):
    # Проверяет передачу источника site в авторизацию из аргумента source_site
    # команды /start.
    await bot_client.send_message(text="/start source_site")
    assert fake_auth.source == "site"


@pytest.mark.parametrize(
    ("payload", "expected_source"),
    [
        ("source_site", "site"),
        ("source_channel", "channel"),
        ("source_ad", "ad"),
        ("source_ref_123", "ref_123"),
    ],
)
@pytest.mark.asyncio
async def test_start_handler_deep_link_various_sources(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
    payload,
    expected_source,
):
    # Проверяет извлечение различных источников из аргумента /start с префиксом
    # source_, включая суффикс с подчёркиванием.
    await bot_client.send_message(text=f"/start {payload}")
    assert fake_auth.source == expected_source


@pytest.mark.asyncio
async def test_start_handler_no_source(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
):
    # Проверяет, что /start без аргумента не задаёт источник пользователя.
    await bot_client.send_message(text="/start")
    assert fake_auth.source is None


@pytest.mark.asyncio
async def test_start_handler_unknown_deep_link_prefix(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
):
    # Проверяет, что аргумент /start с неизвестным префиксом не задаёт источник
    # пользователя.
    await bot_client.send_message(text="/start promo_summer")
    assert fake_auth.source is None


@pytest.mark.asyncio
async def test_start_handler_deep_link_empty_suffix(
    bot_client: BotClient,
    fake_auth: FakeTelegramAuth,
):
    # Проверяет, что аргумент source_ без суффикса не задаёт источник
    # пользователя.
    await bot_client.send_message(text="/start source_")
    assert fake_auth.source is None


# Routers tests


@pytest.mark.asyncio
async def test_router_routes_start_in_private_chat(bot_client: BotClient):
    # Проверяет обработку /start в личном чате с отправкой приветствия и
    # клавиатуры выбора площадки.
    await bot_client.send_message(text="/start", chat_type=ChatType.PRIVATE)
    sent = bot_client.bot.sent_methods[0]
    assert isinstance(sent, SendMessage)
    assert sent.text == onboarding_start_message()
    assert sent.reply_markup == build_onboarding_marketplaces_kbd()


@pytest.mark.asyncio
async def test_router_ignores_other_text(bot_client: BotClient):
    # Проверяет, что обычный текст в личном чате не вызывает обращений к
    # Telegram API.
    await bot_client.send_message(text="hello", chat_type=ChatType.PRIVATE)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_other_command(bot_client: BotClient):
    # Проверяет, что неизвестная команда в личном чате не вызывает обращений к
    # Telegram API.
    await bot_client.send_message(text="/unknown", chat_type=ChatType.PRIVATE)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_group_chat(bot_client: BotClient):
    # Проверяет игнорирование команды /start в групповом чате.
    await bot_client.send_message(text="/start", chat_type=ChatType.GROUP)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_channel_chat(bot_client: BotClient):
    # Проверяет игнорирование команды /start в канале.
    await bot_client.send_message(text="/start", chat_type=ChatType.CHANNEL)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_super_group_chat(bot_client: BotClient):
    # Проверяет игнорирование команды /start в супергруппе.
    await bot_client.send_message(text="/start", chat_type=ChatType.SUPERGROUP)
    assert bot_client.bot.sent_methods == []


@pytest.mark.asyncio
async def test_router_ignores_start_in_sender_chat(bot_client: BotClient):
    # Проверяет игнорирование команды /start при типе чата sender.
    await bot_client.send_message(text="/start", chat_type=ChatType.SENDER)
    assert bot_client.bot.sent_methods == []
