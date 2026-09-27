# ruff: noqa: PLR2004
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid7

import pytest

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from aiogram.types import Chat, InaccessibleMessage, Message
from fakes.telegram_bot import BotClient

from lansly.apps.telegram_bot.keyboards import (
    OnboardingAction,
    OnboardingCB,
)
from lansly.apps.telegram_bot.messages import error_callback_message
from lansly.apps.telegram_bot.states import OnboardingState
from lansly.preferences.exceptions import UserCategoryFollowLimitExceededError
from lansly.projects.consts import Marketplace

pytestmark = pytest.mark.asyncio


async def choose_marketplace(client, state, follow, source="fl"):
    await state.set_state(OnboardingState.select_marketplace)
    await client.click(
        OnboardingCB(
            action=OnboardingAction.MARKETPLACE,
            marketplace=source,
        ).pack(),
    )
    return follow.directions[source][0]


async def choose_direction(client, follow, direction):
    await client.click(
        OnboardingCB(
            action=OnboardingAction.DIRECTION,
            category_id=direction.id,
        ).pack(),
    )
    return follow.categories[direction.id][0]


@pytest.mark.parametrize("source", ["fl", "kwork"])
async def test_select_marketplace(
    bot_client,
    state,
    fake_follow_service,
    source,
):
    # Проверяет переход от выбора площадки к направлениям, сохранение их в FSM
    # и передачу ID направления в кнопку.
    root = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source=source,
    )
    assert await state.get_state() == OnboardingState.select_direction.state
    assert await state.get_data() == {
        "marketplace": source,
        "directions": {str(root.id): root.title},
    }
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert edited_message.reply_markup is not None
    direction_button = edited_message.reply_markup.inline_keyboard[0][0]
    assert direction_button.callback_data is not None
    callback_data = OnboardingCB.unpack(direction_button.callback_data)

    assert callback_data.category_id == root.id


async def test_marketplace_selection_continues_when_message_is_not_modified(
    bot_client: BotClient,
    state,
    fake_follow_service,
):
    # Неизменившееся сообщение не мешает перейти к направлениям и ответить
    # на callback.
    bot_client.bot.set_method_error(
        EditMessageText,
        lambda method: TelegramBadRequest(
            method=method,
            message="Bad Request: message is not modified",
        ),
    )

    root = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source=Marketplace.FL,
    )

    assert await state.get_state() == OnboardingState.select_direction.state
    assert await state.get_data() == {
        "marketplace": Marketplace.FL,
        "directions": {str(root.id): root.title},
    }
    assert [type(method) for method in bot_client.bot.sent_methods] == [
        EditMessageText,
        AnswerCallbackQuery,
    ]


async def test_marketplace_selection_routes_bad_request_to_global_handler(
    bot_client,
    state,
    fake_follow_service,
    caplog,
):
    # Другую ошибку передаём общему обработчику: показываем alert и остаёмся
    # на выборе площадки.
    bot_client.bot.set_method_error(
        EditMessageText,
        lambda method: TelegramBadRequest(
            method=method,
            message="Bad Request: message to edit not found",
        ),
    )

    await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source=Marketplace.FL,
    )

    assert await state.get_state() == OnboardingState.select_marketplace.state
    assert [type(method) for method in bot_client.bot.sent_methods] == [
        EditMessageText,
        AnswerCallbackQuery,
    ]
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.text == error_callback_message()
    assert callback_answer.show_alert is True
    assert any(
        record.name == "lansly.apps.telegram_bot.handlers.errors"
        and record.getMessage() == "Unhandled exceptions"
        and record.exc_info is not None
        and isinstance(record.exc_info[1], TelegramBadRequest)
        and "message to edit not found" in str(record.exc_info[1])
        for record in caplog.records
    )


async def test_select_direction(bot_client, state, fake_follow_service):
    # Проверяет переход к выбору категории с сохранением доступных категорий в
    # FSM и показом второго шага.
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
    )
    child = await choose_direction(bot_client, fake_follow_service, direction)
    assert await state.get_state() == OnboardingState.select_category.state
    assert (await state.get_data())["categories"] == {
        str(child.id): child.title,
    }
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert "Шаг 2 из 2" in edited_message.text


async def test_select_category(bot_client, state, fake_follow_service):
    # Проверяет подписку на выбранную категорию, очистку FSM и показ результата
    # без всплывающей ошибки.
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
    )
    child = await choose_direction(bot_client, fake_follow_service, direction)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    assert fake_follow_service.followed == {child.id}
    assert await state.get_state() is None
    assert await state.get_data() == {}
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert child.title in edited_message.text
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is not True


@pytest.mark.parametrize(
    ("pro", "admin", "expected"),
    [
        (False, False, "pro_subscription"),
        (True, False, "manage_subscription"),
        (False, True, None),
    ],
)
async def test_complete_user_roles(
    *,
    bot_client,
    state,
    fake_follow_service,
    fake_auth,
    pro,
    admin,
    expected,
):
    # Проверяет кнопки покупки и управления подпиской после онбординга для
    # FREE, PRO и администратора.
    fake_auth.result = replace(fake_auth.result, is_pro=pro, is_admin=admin)
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
    )
    child = await choose_direction(bot_client, fake_follow_service, direction)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert edited_message.reply_markup is not None
    keyboard = edited_message.reply_markup.inline_keyboard
    callback_data = {
        button.callback_data for row in keyboard for button in row
    }
    if expected is not None:
        assert expected in callback_data
    else:
        assert not callback_data & {"pro_subscription", "manage_subscription"}


async def test_category_limit_exceeded(bot_client, state, fake_follow_service):
    # Проверяет показ ошибки с лимитом категорий без изменения данных FSM, шага
    # онбординга и подписок.
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
    )
    child = await choose_direction(bot_client, fake_follow_service, direction)
    before = await state.get_data()
    fake_follow_service.error = UserCategoryFollowLimitExceededError(limit=1)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True
    assert "1" in callback_answer.text
    assert await state.get_state() == OnboardingState.select_category.state
    assert await state.get_data() == before
    assert not fake_follow_service.followed


async def test_back_to_marketplaces(bot_client, state, fake_follow_service):
    # Проверяет возврат к шагу выбора площадки с двумя кнопками площадок.
    await choose_marketplace(bot_client, state, fake_follow_service)
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_MARKETPLACES).pack(),
    )
    assert await state.get_state() == OnboardingState.select_marketplace.state
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert edited_message.reply_markup is not None
    keyboard = edited_message.reply_markup.inline_keyboard
    keyboard_buttons = [button for row in keyboard for button in row]
    assert len(keyboard_buttons) == 2


async def test_back_to_directions(bot_client, state, fake_follow_service):
    # Проверяет возврат к выбору направления с показом первого шага онбординга.
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
    )
    await choose_direction(bot_client, fake_follow_service, direction)
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_DIRECTIONS).pack(),
    )
    assert await state.get_state() == OnboardingState.select_direction.state
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert "Шаг 1 из 2" in edited_message.text


async def test_switch_marketplace(bot_client, state, fake_follow_service):
    # Проверяет замену площадки и доступных категорий в FSM при переходе с
    # FL.ru на Kwork.
    old_direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source="fl",
    )
    old = await choose_direction(
        bot_client,
        fake_follow_service,
        old_direction,
    )
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_DIRECTIONS).pack(),
    )
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_MARKETPLACES).pack(),
    )
    new_direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source="kwork",
    )
    new = await choose_direction(
        bot_client,
        fake_follow_service,
        new_direction,
    )
    data = await state.get_data()
    assert data["marketplace"] == "kwork"
    assert str(old.id) not in data["categories"]
    assert str(new.id) in data["categories"]


async def test_empty_directions(bot_client, state, category_service):
    # Проверяет, что при отсутствии направлений FSM содержит пустой словарь, а
    # клавиатура — одну кнопку возврата.
    category_service.gateway.existing = []
    await state.set_state(OnboardingState.select_marketplace)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.MARKETPLACE,
            marketplace="fl",
        ).pack(),
    )
    assert (await state.get_data())["directions"] == {}
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert edited_message.reply_markup is not None
    keyboard = edited_message.reply_markup.inline_keyboard
    keyboard_buttons = [button for row in keyboard for button in row]
    assert len(keyboard_buttons) == 1


async def test_empty_categories(
    bot_client,
    state,
    category_service,
    fake_follow_service,
):
    # Проверяет, что при отсутствии подкатегорий FSM содержит пустой словарь, а
    # клавиатура — одну кнопку возврата.
    root = await choose_marketplace(bot_client, state, fake_follow_service)
    category_service.gateway.existing = [root]
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.DIRECTION,
            category_id=root.id,
        ).pack(),
    )
    assert (await state.get_data())["categories"] == {}
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert edited_message.reply_markup is not None
    keyboard = edited_message.reply_markup.inline_keyboard
    keyboard_buttons = [button for row in keyboard for button in row]
    assert len(keyboard_buttons) == 1


@pytest.mark.parametrize(
    ("action", "step"),
    [
        (OnboardingAction.MARKETPLACE, OnboardingState.select_marketplace),
        (OnboardingAction.DIRECTION, OnboardingState.select_direction),
        (OnboardingAction.CATEGORY, OnboardingState.select_category),
    ],
)
async def test_missing_callback_fields(bot_client, state, action, step):
    # Проверяет показ всплывающей ошибки, если callback онбординга не содержит
    # обязательных данных выбранного действия.
    await state.set_state(step)
    await bot_client.click(OnboardingCB(action=action).pack())
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True


@pytest.mark.parametrize(
    ("action", "step"),
    [
        (OnboardingAction.DIRECTION, OnboardingState.select_direction),
        (OnboardingAction.CATEGORY, OnboardingState.select_category),
        (OnboardingAction.BACK_TO_DIRECTIONS, OnboardingState.select_category),
    ],
)
async def test_missing_state_data(bot_client, state, action, step):
    # Проверяет показ всплывающей ошибки без заполнения FSM, если данные
    # текущего шага отсутствуют.
    await state.set_state(step)
    await bot_client.click(
        OnboardingCB(action=action, category_id=uuid7()).pack(),
    )
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True
    assert await state.get_data() == {}


async def test_unknown_direction(bot_client, state, fake_follow_service):
    # Проверяет отказ при выборе неизвестного направления с сохранением шага
    # выбора направления.
    await choose_marketplace(bot_client, state, fake_follow_service)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.DIRECTION,
            category_id=uuid7(),
        ).pack(),
    )
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True
    assert await state.get_state() == OnboardingState.select_direction.state


async def test_unknown_category(bot_client, state, fake_follow_service):
    # Проверяет показ ошибки при выборе неизвестной категории без добавления
    # подписки.
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
    )
    await choose_direction(bot_client, fake_follow_service, direction)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=uuid7(),
        ).pack(),
    )
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True
    assert not fake_follow_service.followed


async def test_inaccessible_message(bot_client, state):
    # Проверяет показ ошибки для недоступного сообщения без изменения шага
    # онбординга.
    await state.set_state(OnboardingState.select_direction)
    message = InaccessibleMessage(
        chat=Chat(id=1, type="private"),
        message_id=1,
        date=0,
    )
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_MARKETPLACES).pack(),
        message=message,
    )
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True
    assert await state.get_state() == OnboardingState.select_direction.state


async def test_expired_callback(bot_client):
    # Проверяет показ всплывающей ошибки при нажатии кнопки выбора категории
    # вне активного онбординга.
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=uuid7(),
        ).pack(),
    )
    callback_answer = bot_client.bot.get_last_method(AnswerCallbackQuery)
    assert callback_answer.show_alert is True


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
async def test_private_chat_only(bot_client, chat_type):
    # Проверяет, что callback онбординга из группы, супергруппы или канала не
    # вызывает обращений к Telegram API.
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type=chat_type),
    )
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_MARKETPLACES).pack(),
        message=message,
    )
    assert bot_client.bot.sent_methods == []


async def test_full_kwork_flow(bot_client, state, fake_follow_service):
    # Проверяет сценарий от /start до подписки на категорию Kwork с завершением
    # FSM и указанием площадки в результате.
    await bot_client.send_message("/start")
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source="kwork",
    )
    child = await choose_direction(bot_client, fake_follow_service, direction)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert "KWORK" in edited_message.text
    assert child.id in fake_follow_service.followed
    assert await state.get_state() is None


async def test_full_fl_flow(bot_client, state, fake_follow_service):
    # Проверяет сценарий от /start до подписки на категорию FL.ru с завершением
    # FSM и указанием площадки в результате.
    await bot_client.send_message("/start")
    direction = await choose_marketplace(
        bot_client,
        state,
        fake_follow_service,
        source="fl",
    )
    child = await choose_direction(bot_client, fake_follow_service, direction)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    edited_message = bot_client.bot.get_last_method(EditMessageText)
    assert "FL" in edited_message.text
    assert child.id in fake_follow_service.followed
    assert await state.get_state() is None
