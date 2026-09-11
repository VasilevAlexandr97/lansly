# ruff: noqa: PLR2004
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid7

import pytest

from aiogram.types import Chat, InaccessibleMessage, Message
from fakes.bot_scenarios import buttons, last_answer, last_screen, settings

from lansly.apps.telegram_bot.keyboards import (
    CategorySettingsAction,
    CategorySettingsCB,
)
from lansly.apps.telegram_bot.states import CategorySettingsState
from lansly.preferences.exceptions import UserCategoryFollowLimitExceededError

pytestmark = pytest.mark.asyncio


async def test_open_settings(bot_client, state):
    # Проверяет открытие настроек на выборе площадки с очисткой прежних данных
    # FSM и показом четырёх кнопок.
    await state.set_state("other")
    await state.set_data({"old": 1})
    await bot_client.click(
        CategorySettingsCB(action=CategorySettingsAction.OPEN).pack(),
    )
    assert (
        await state.get_state()
        == CategorySettingsState.select_marketplace.state
    )
    assert await state.get_data() == {}
    assert len(buttons(last_screen(bot_client))) == 4


@pytest.mark.parametrize("source", ["fl", "kwork"])
async def test_select_marketplace(
    bot_client,
    state,
    fake_follow_service,
    source,
):
    # Проверяет загрузку направлений выбранной площадки, сохранение их в FSM и
    # переход к выбору направления.
    root = await settings(bot_client, fake_follow_service, source, "direction")
    assert (
        await state.get_state() == CategorySettingsState.select_direction.state
    )
    assert await state.get_data() == {
        "marketplace": source,
        "directions": {str(root.id): root.title},
    }
    assert ("directions", source) in fake_follow_service.calls


async def test_select_direction(bot_client, state, fake_follow_service):
    # Проверяет переход к выбору категории с сохранением названия направления и
    # доступных категорий в FSM.
    child = await settings(bot_client, fake_follow_service)
    data = await state.get_data()
    assert data["direction_title"] == "Дизайн"
    assert data["categories"] == {
        str(child.id): child.title,
    }
    assert (
        await state.get_state() == CategorySettingsState.select_category.state
    )


async def test_toggle_category(bot_client, state, fake_follow_service):
    # Проверяет включение и отключение категории повторными нажатиями с
    # обновлением отметки кнопки и сохранением шага.
    child = await settings(bot_client, fake_follow_service)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.TOGGLE,
            category_id=child.id,
        ).pack(),
    )
    assert child.id in fake_follow_service.followed
    assert buttons(
        last_screen(bot_client),
    )[0].text.startswith("✅")
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.TOGGLE,
            category_id=child.id,
        ).pack(),
    )
    assert child.id not in fake_follow_service.followed
    assert buttons(
        last_screen(bot_client),
    )[0].text.startswith("⬜")
    assert (
        await state.get_state() == CategorySettingsState.select_category.state
    )


async def test_toggle_limit_exceeded(bot_client, state, fake_follow_service):
    # Проверяет показ ошибки лимита без замены экрана и выхода из шага выбора
    # категории.
    child = await settings(bot_client, fake_follow_service)
    before = last_screen(bot_client)
    fake_follow_service.error = UserCategoryFollowLimitExceededError(limit=1)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.TOGGLE,
            category_id=child.id,
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
    assert last_screen(bot_client) is before
    assert (
        await state.get_state() == CategorySettingsState.select_category.state
    )


async def test_back_to_directions(bot_client, state, fake_follow_service):
    # Проверяет возврат к направлениям с обновлённым счётчиком после включения
    # подписки на категорию.
    child = await settings(bot_client, fake_follow_service)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.TOGGLE,
            category_id=child.id,
        ).pack(),
    )
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.BACK_TO_DIRECTIONS,
        ).pack(),
    )
    assert "[1/1]" in buttons(last_screen(bot_client))[0].text
    assert (
        await state.get_state() == CategorySettingsState.select_direction.state
    )


@pytest.mark.parametrize(
    "step",
    [
        CategorySettingsState.select_direction,
        CategorySettingsState.confirm_disable_monitoring,
    ],
)
async def test_back_to_marketplaces(bot_client, state, step):
    # Проверяет возврат к выбору площадки из направления или подтверждения
    # отключения с очисткой данных FSM.
    await state.set_state(step)
    await state.set_data({"marketplace": "fl"})
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.BACK_TO_MARKETPLACES,
        ).pack(),
    )
    assert (
        await state.get_state()
        == CategorySettingsState.select_marketplace.state
    )
    assert await state.get_data() == {}


async def test_request_disable_all(bot_client, state, fake_follow_service):
    # Проверяет переход к подтверждению отключения мониторинга без немедленной
    # отписки.
    await settings(bot_client, fake_follow_service, step="marketplace")
    await bot_client.click(
        CategorySettingsCB(action=CategorySettingsAction.DISABLE_ALL).pack(),
    )
    assert (
        await state.get_state()
        == CategorySettingsState.confirm_disable_monitoring.state
    )
    assert ("disable",) not in fake_follow_service.calls


async def test_cancel_disable_all(bot_client, state, fake_follow_service):
    # Проверяет, что отмена отключения возвращает к площадкам и сохраняет
    # существующие подписки.
    fake_follow_service.followed.add(uuid7())
    before = set(fake_follow_service.followed)
    await settings(bot_client, fake_follow_service, step="marketplace")
    await bot_client.click(
        CategorySettingsCB(action=CategorySettingsAction.DISABLE_ALL).pack(),
    )
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.BACK_TO_MARKETPLACES,
        ).pack(),
    )
    assert fake_follow_service.followed == before
    assert (
        await state.get_state()
        == CategorySettingsState.select_marketplace.state
    )


async def test_confirm_disable_all(bot_client, state, fake_follow_service):
    # Проверяет отключение всех подписок после подтверждения с очисткой
    # состояния и данных FSM.
    fake_follow_service.followed.update(
        c.id for cats in fake_follow_service.categories.values() for c in cats
    )
    await state.set_state(CategorySettingsState.confirm_disable_monitoring)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.CONFIRM_DISABLE_ALL,
        ).pack(),
    )
    assert not fake_follow_service.followed
    assert ("disable",) in fake_follow_service.calls
    assert await state.get_state() is None
    assert await state.get_data() == {}


@pytest.mark.parametrize(
    ("pro", "admin", "expected"),
    [
        (False, False, "pro_subscription"),
        (True, False, "manage_subscription"),
        (False, True, None),
    ],
)
async def test_confirm_disable_roles(
    *,
    bot_client,
    state,
    fake_auth,
    pro,
    admin,
    expected,
):
    # Проверяет кнопки подписки после отключения мониторинга для FREE, PRO и
    # администратора.
    fake_auth.result = replace(fake_auth.result, is_pro=pro, is_admin=admin)
    await state.set_state(CategorySettingsState.confirm_disable_monitoring)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.CONFIRM_DISABLE_ALL,
        ).pack(),
    )
    data = {b.callback_data for b in buttons(last_screen(bot_client))}
    assert (
        (expected in data)
        if expected
        else not data & {"pro_subscription", "manage_subscription"}
    )


async def test_empty_directions(bot_client, state, fake_follow_service):
    # Проверяет пустой словарь направлений в FSM и две навигационные кнопки,
    # если направлений площадки нет.
    fake_follow_service.directions["fl"] = []
    await state.set_state(CategorySettingsState.select_marketplace)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.MARKETPLACE,
            marketplace="fl",
        ).pack(),
    )
    assert (await state.get_data())["directions"] == {}
    assert (
        len(
            buttons(last_screen(bot_client)),
        )
        == 2
    )


async def test_empty_categories(bot_client, state, fake_follow_service):
    # Проверяет пустой словарь категорий в FSM и две навигационные кнопки, если
    # у направления нет подкатегорий.
    root = await settings(bot_client, fake_follow_service, step="direction")
    fake_follow_service.categories[root.id] = []
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.DIRECTION,
            category_id=root.id,
        ).pack(),
    )
    assert (await state.get_data())["categories"] == {}
    assert (
        len(
            buttons(last_screen(bot_client)),
        )
        == 2
    )


@pytest.mark.parametrize(
    ("action", "step"),
    [
        (
            CategorySettingsAction.MARKETPLACE,
            CategorySettingsState.select_marketplace,
        ),
        (
            CategorySettingsAction.DIRECTION,
            CategorySettingsState.select_direction,
        ),
        (CategorySettingsAction.TOGGLE, CategorySettingsState.select_category),
    ],
)
async def test_missing_callback_fields(bot_client, state, action, step):
    # Проверяет показ всплывающей ошибки при отсутствии обязательных полей
    # callback настроек.
    await state.set_state(step)
    await bot_client.click(CategorySettingsCB(action=action).pack())
    assert last_answer(bot_client).show_alert


@pytest.mark.parametrize(
    ("action", "step"),
    [
        (
            CategorySettingsAction.DIRECTION,
            CategorySettingsState.select_direction,
        ),
        (CategorySettingsAction.TOGGLE, CategorySettingsState.select_category),
        (
            CategorySettingsAction.BACK_TO_DIRECTIONS,
            CategorySettingsState.select_category,
        ),
    ],
)
async def test_missing_state_data(bot_client, state, action, step):
    # Проверяет показ всплывающей ошибки, если в FSM отсутствуют данные для
    # выбранного действия настроек.
    await state.set_state(step)
    await bot_client.click(
        CategorySettingsCB(action=action, category_id=uuid7()).pack(),
    )
    assert last_answer(bot_client).show_alert


async def test_unknown_direction(bot_client, state, fake_follow_service):
    # Проверяет отказ при выборе неизвестного направления с сохранением
    # текущего шага настроек.
    await settings(bot_client, fake_follow_service, step="direction")
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.DIRECTION,
            category_id=uuid7(),
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
    assert (
        await state.get_state() == CategorySettingsState.select_direction.state
    )


async def test_unknown_category(bot_client, fake_follow_service):
    # Проверяет отказ при выборе неизвестной категории без вызова переключения
    # подписки.
    await settings(bot_client, fake_follow_service)
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.TOGGLE,
            category_id=uuid7(),
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
    assert not any(c[0] == "toggle" for c in fake_follow_service.calls)


@pytest.mark.parametrize(
    ("action", "step"),
    [
        (CategorySettingsAction.OPEN, None),
        (
            CategorySettingsAction.MARKETPLACE,
            CategorySettingsState.select_marketplace,
        ),
        (
            CategorySettingsAction.BACK_TO_MARKETPLACES,
            CategorySettingsState.select_direction,
        ),
    ],
)
async def test_inaccessible_message(bot_client, state, action, step):
    # Проверяет показ ошибки для недоступного сообщения без изменения состояния
    # настроек.
    await state.set_state(step)
    msg = InaccessibleMessage(
        chat=Chat(id=1, type="private"),
        message_id=1,
        date=0,
    )
    await bot_client.click(
        CategorySettingsCB(action=action, marketplace="fl").pack(),
        message=msg,
    )
    assert last_answer(bot_client).show_alert
    assert await state.get_state() == (step.state if step else None)


@pytest.mark.parametrize(
    ("action", "step"),
    [
        (
            CategorySettingsAction.DISABLE_ALL,
            CategorySettingsState.select_marketplace,
        ),
        (
            CategorySettingsAction.CONFIRM_DISABLE_ALL,
            CategorySettingsState.confirm_disable_monitoring,
        ),
    ],
)
async def test_disable_inaccessible_message(
    bot_client,
    state,
    fake_follow_service,
    action,
    step,
):
    # Проверяет, что отключение из недоступного сообщения подтверждает callback
    # без alert, но не меняет FSM и подписки.
    await state.set_state(step)
    msg = InaccessibleMessage(
        chat=Chat(id=1, type="private"),
        message_id=1,
        date=0,
    )
    await bot_client.click(
        CategorySettingsCB(action=action).pack(),
        message=msg,
    )
    assert last_answer(bot_client).show_alert is not True
    assert await state.get_state() == step.state
    assert ("disable",) not in fake_follow_service.calls


async def test_expired_callback(bot_client, fake_follow_service):
    # Проверяет показ ошибки для устаревшей кнопки подтверждения без отключения
    # подписок.
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.CONFIRM_DISABLE_ALL,
        ).pack(),
    )
    assert last_answer(bot_client).show_alert
    assert ("disable",) not in fake_follow_service.calls


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
async def test_private_chat_only(bot_client, chat_type):
    # Проверяет, что открытие настроек из группы, супергруппы или канала не
    # вызывает обращений к Telegram API.
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type=chat_type),
    )
    await bot_client.click(
        CategorySettingsCB(action=CategorySettingsAction.OPEN).pack(),
        message=msg,
    )
    assert not bot_client.bot.sent_methods


async def test_full_multisource_flow(bot_client, state, fake_follow_service):
    # Проверяет подписку на категории обеих площадок с обновлением счётчиков и
    # последующее отключение всех подписок.
    for source in ["fl", "kwork"]:
        child = await settings(bot_client, fake_follow_service, source)
        await bot_client.click(
            CategorySettingsCB(
                action=CategorySettingsAction.TOGGLE,
                category_id=child.id,
            ).pack(),
        )
        await bot_client.click(
            CategorySettingsCB(
                action=CategorySettingsAction.BACK_TO_DIRECTIONS,
            ).pack(),
        )
        assert "[1/1]" in buttons(last_screen(bot_client))[0].text
    assert len(fake_follow_service.followed) == 2
    await settings(bot_client, fake_follow_service, step="marketplace")
    await bot_client.click(
        CategorySettingsCB(action=CategorySettingsAction.DISABLE_ALL).pack(),
    )
    await bot_client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.CONFIRM_DISABLE_ALL,
        ).pack(),
    )
    assert not fake_follow_service.followed
    assert await state.get_state() is None
