# ruff: noqa: PLR2004
from dataclasses import replace

import pytest

from aiogram.methods import DeleteMessage
from fakes.bot_scenarios import buttons, last_screen

from lansly.apps.telegram_bot.keyboards import MainMenuCB
from lansly.apps.telegram_bot.states import OnboardingState
from lansly.preferences.dto import SourceCategoryFollowCountDTO as Count

pytestmark = pytest.mark.asyncio


async def test_start_new_user_state(bot_client, state):
    # Проверяет, что /start для нового пользователя переводит FSM к выбору
    # площадки и удаляет прежние данные.
    await state.set_data({"old": 1})
    await bot_client.send_message("/start")
    assert await state.get_state() == OnboardingState.select_marketplace.state
    assert await state.get_data() == {}


@pytest.mark.parametrize(
    "step",
    [
        OnboardingState.select_marketplace,
        OnboardingState.select_direction,
        OnboardingState.select_category,
    ],
)
async def test_start_resume_onboarding(bot_client, state, fake_auth, step):
    # Проверяет, что /start на любом шаге незавершённого онбординга начинает
    # выбор площадки заново и очищает данные.
    fake_auth.result = replace(fake_auth.result, is_new=False)
    await state.set_state(step)
    await state.set_data({"old": 1})
    await bot_client.send_message("/start")
    assert await state.get_state() == OnboardingState.select_marketplace.state
    assert await state.get_data() == {}


async def test_start_existing_without_follows(bot_client, fake_auth):
    # Проверяет показ главного меню с предложением выбрать категории
    # существующему пользователю без подписок.
    fake_auth.result = replace(fake_auth.result, is_new=False)
    await bot_client.send_message("/start")
    assert "Главное меню" in last_screen(bot_client).text
    assert "Выберите категории" in last_screen(bot_client).text


async def test_start_existing_other_state(bot_client, state, fake_auth):
    # Проверяет, что /start существующего пользователя очищает постороннее
    # состояние и данные FSM.
    fake_auth.result = replace(fake_auth.result, is_new=False)
    await state.set_state("other")
    await state.set_data({"old": 1})
    await bot_client.send_message("/start")
    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_menu_command(bot_client, state, fake_follow_service):
    # Проверяет показ счётчиков подписок обеих площадок по /menu и сброс
    # текущего состояния FSM.
    fake_follow_service.follow_counts = [Count("fl", 2), Count("kwork", 3)]
    await state.set_state("other")
    await bot_client.send_message("/menu")
    assert "FL - 2" in last_screen(bot_client).text
    assert "KWORK - 3" in last_screen(bot_client).text
    assert await state.get_state() is None


async def test_menu_callback_keep_message(bot_client):
    # Проверяет открытие главного меню по callback с delete_message=False без
    # удаления исходного сообщения.
    await bot_client.click(MainMenuCB(delete_message=False).pack())
    assert not any(
        isinstance(m, DeleteMessage) for m in bot_client.bot.sent_methods
    )
    assert "Главное меню" in last_screen(bot_client).text


async def test_menu_callback_delete_message(bot_client, state):
    # Проверяет, что callback меню с delete_message=True сначала удаляет
    # сообщение и очищает состояние FSM.
    await state.set_state("other")
    await bot_client.click(MainMenuCB(delete_message=True).pack())
    assert isinstance(bot_client.bot.sent_methods[0], DeleteMessage)
    assert await state.get_state() is None


@pytest.mark.parametrize(
    ("pro", "admin", "expected"),
    [
        (False, False, "pro_subscription"),
        (True, False, "manage_subscription"),
        (False, True, None),
    ],
)
async def test_menu_roles(bot_client, fake_auth, pro, admin, expected):
    # Проверяет кнопки покупки и управления подпиской в меню для FREE, PRO и
    # администратора.
    fake_auth.result = replace(fake_auth.result, is_pro=pro, is_admin=admin)
    await bot_client.send_message("/menu")
    data = {b.callback_data for b in buttons(last_screen(bot_client))}
    assert (
        (expected in data)
        if expected
        else not data & {"pro_subscription", "manage_subscription"}
    )


async def test_menu_refresh_counts(bot_client, fake_follow_service):
    # Проверяет повторную загрузку счётчиков при каждом /menu и предложение
    # выбрать категории при нулевом счётчике.
    for count in [1, 2, 0]:
        fake_follow_service.follow_counts = [Count("fl", count)]
        await bot_client.send_message("/menu")
        assert (
            (f"FL - {count}" in last_screen(bot_client).text)
            if count
            else ("Выберите категории" in last_screen(bot_client).text)
        )
    assert fake_follow_service.follow_counts_calls == 3
