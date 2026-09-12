# ruff: noqa: PLR2004
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid7

import pytest

from aiogram.types import Chat, InaccessibleMessage, Message
from fakes.bot_scenarios import buttons, last_answer, last_screen, onboard

from lansly.apps.telegram_bot.keyboards import (
    OnboardingAction,
    OnboardingCB,
)
from lansly.apps.telegram_bot.states import OnboardingState
from lansly.preferences.exceptions import UserCategoryFollowLimitExceededError

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("source", ["fl", "kwork"])
async def test_select_marketplace(
    bot_client,
    state,
    fake_follow_service,
    source,
):
    # Проверяет переход от выбора площадки к направлениям, сохранение их в FSM
    # и передачу ID направления в кнопку.
    root = await onboard(
        bot_client,
        state,
        fake_follow_service,
        source,
        "direction",
    )
    assert await state.get_state() == OnboardingState.select_direction.state
    assert await state.get_data() == {
        "marketplace": source,
        "directions": {str(root.id): root.title},
    }
    assert (
        OnboardingCB.unpack(
            buttons(last_screen(bot_client))[0].callback_data,
        ).category_id
        == root.id
    )


async def test_select_direction(bot_client, state, fake_follow_service):
    # Проверяет переход к выбору категории с сохранением доступных категорий в
    # FSM и показом второго шага.
    child = await onboard(bot_client, state, fake_follow_service)
    assert await state.get_state() == OnboardingState.select_category.state
    assert (await state.get_data())["categories"] == {
        str(child.id): child.title,
    }
    assert "Шаг 2 из 2" in last_screen(bot_client).text


async def test_select_category(bot_client, state, fake_follow_service):
    # Проверяет подписку на выбранную категорию, очистку FSM и показ результата
    # без всплывающей ошибки.
    child = await onboard(bot_client, state, fake_follow_service)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    assert fake_follow_service.followed == {child.id}
    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert child.title in last_screen(bot_client).text
    assert last_answer(bot_client).show_alert is not True


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
    child = await onboard(bot_client, state, fake_follow_service)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    data = {b.callback_data for b in buttons(last_screen(bot_client))}
    assert (
        (expected in data)
        if expected
        else not data & {"pro_subscription", "manage_subscription"}
    )


async def test_category_limit_exceeded(bot_client, state, fake_follow_service):
    # Проверяет показ ошибки с лимитом категорий без изменения данных FSM, шага
    # онбординга и подписок.
    child = await onboard(bot_client, state, fake_follow_service)
    before = await state.get_data()
    fake_follow_service.error = UserCategoryFollowLimitExceededError(limit=1)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
    assert "1" in last_answer(bot_client).text
    assert await state.get_state() == OnboardingState.select_category.state
    assert await state.get_data() == before
    assert not fake_follow_service.followed


async def test_back_to_marketplaces(bot_client, state, fake_follow_service):
    # Проверяет возврат к шагу выбора площадки с двумя кнопками площадок.
    await onboard(bot_client, state, fake_follow_service, step="direction")
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_MARKETPLACES).pack(),
    )
    assert await state.get_state() == OnboardingState.select_marketplace.state
    assert len(buttons(last_screen(bot_client))) == 2


async def test_back_to_directions(bot_client, state, fake_follow_service):
    # Проверяет возврат к выбору направления с показом первого шага онбординга.
    await onboard(bot_client, state, fake_follow_service)
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_DIRECTIONS).pack(),
    )
    assert await state.get_state() == OnboardingState.select_direction.state
    assert "Шаг 1 из 2" in last_screen(bot_client).text


async def test_switch_marketplace(bot_client, state, fake_follow_service):
    # Проверяет замену площадки и доступных категорий в FSM при переходе с
    # FL.ru на Kwork.
    old = await onboard(bot_client, state, fake_follow_service, "fl")
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_DIRECTIONS).pack(),
    )
    await bot_client.click(
        OnboardingCB(action=OnboardingAction.BACK_TO_MARKETPLACES).pack(),
    )
    new = await onboard(bot_client, state, fake_follow_service, "kwork")
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
    assert len(buttons(last_screen(bot_client))) == 1


async def test_empty_categories(
    bot_client,
    state,
    category_service,
    fake_follow_service,
):
    # Проверяет, что при отсутствии подкатегорий FSM содержит пустой словарь, а
    # клавиатура — одну кнопку возврата.
    root = await onboard(
        bot_client,
        state,
        fake_follow_service,
        step="direction",
    )
    category_service.gateway.existing = [root]
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.DIRECTION,
            category_id=root.id,
        ).pack(),
    )
    assert (await state.get_data())["categories"] == {}
    assert len(buttons(last_screen(bot_client))) == 1


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
    assert last_answer(bot_client).show_alert


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
    assert last_answer(bot_client).show_alert
    assert await state.get_data() == {}


async def test_unknown_direction(bot_client, state, fake_follow_service):
    # Проверяет отказ при выборе неизвестного направления с сохранением шага
    # выбора направления.
    await onboard(bot_client, state, fake_follow_service, step="direction")
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.DIRECTION,
            category_id=uuid7(),
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
    assert await state.get_state() == OnboardingState.select_direction.state


async def test_unknown_category(bot_client, state, fake_follow_service):
    # Проверяет показ ошибки при выборе неизвестной категории без добавления
    # подписки.
    await onboard(bot_client, state, fake_follow_service)
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=uuid7(),
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
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
    assert last_answer(bot_client).show_alert
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
    assert last_answer(bot_client).show_alert


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
    child = await onboard(bot_client, state, fake_follow_service, "kwork")
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    assert "KWORK" in last_screen(bot_client).text
    assert child.id in fake_follow_service.followed
    assert await state.get_state() is None


async def test_full_fl_flow(bot_client, state, fake_follow_service):
    # Проверяет сценарий от /start до подписки на категорию FL.ru с завершением
    # FSM и указанием площадки в результате.
    await bot_client.send_message("/start")
    child = await onboard(bot_client, state, fake_follow_service, "fl")
    await bot_client.click(
        OnboardingCB(
            action=OnboardingAction.CATEGORY,
            category_id=child.id,
        ).pack(),
    )
    assert "FL" in last_screen(bot_client).text
    assert child.id in fake_follow_service.followed
    assert await state.get_state() is None
