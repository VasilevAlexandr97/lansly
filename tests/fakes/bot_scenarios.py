from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from lansly.apps.telegram_bot.keyboards import (
    CategorySettingsAction,
    CategorySettingsCB,
    OnboardingAction,
    OnboardingCB,
)
from lansly.apps.telegram_bot.states import (
    OnboardingState,
)


def buttons(method):
    return [b for row in method.reply_markup.inline_keyboard for b in row]


def last_screen(client):
    return next(
        m
        for m in reversed(client.bot.sent_methods)
        if isinstance(m, (EditMessageText, SendMessage))
    )


def last_answer(client):
    return next(
        m
        for m in reversed(client.bot.sent_methods)
        if isinstance(m, AnswerCallbackQuery)
    )


async def onboard(client, state, follow, source="fl", step="category"):
    await state.set_state(OnboardingState.select_marketplace)
    await client.click(
        OnboardingCB(
            action=OnboardingAction.MARKETPLACE,
            marketplace=source,
        ).pack(),
    )
    root = follow.directions[source][0]
    if step == "direction":
        return root
    await client.click(
        OnboardingCB(
            action=OnboardingAction.DIRECTION,
            category_id=root.id,
        ).pack(),
    )
    return follow.categories[root.id][0]


async def settings(client, follow, source="fl", step="category"):
    await client.click(
        CategorySettingsCB(action=CategorySettingsAction.OPEN).pack(),
    )
    if step == "marketplace":
        return None
    await client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.MARKETPLACE,
            marketplace=source,
        ).pack(),
    )
    root = follow.directions[source][0]
    if step == "direction":
        return root
    await client.click(
        CategorySettingsCB(
            action=CategorySettingsAction.DIRECTION,
            category_id=root.id,
        ).pack(),
    )
    return follow.categories[root.id][0]
