import logging

from uuid import uuid7

import pytest

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    Update,
    User,
)
from fakes.projects import FakeProjectProposalRequestService
from fakes.telegram_bot import BotClient, FakeBot

from lansly.apps.telegram_bot.handlers.errors import router as errors_router
from lansly.apps.telegram_bot.keyboards import GenerateProposalCB
from lansly.apps.telegram_bot.messages import (
    error_callback_message,
    profile_not_set_message,
)
from lansly.preferences.exceptions import UserFreelancerProfileNotFoundError

pytestmark = pytest.mark.asyncio


def make_forbidden_event(
    bot: FakeBot,
    description: str,
    update_id: int,
) -> ErrorEvent:
    call = CallbackQuery(
        id=f"callback-{update_id}",
        from_user=User(id=2, is_bot=False, first_name="User"),
        chat_instance="1",
        data="generate_proposal",
    ).as_(bot)
    return ErrorEvent(
        update=Update(update_id=update_id, callback_query=call),
        exception=TelegramForbiddenError(
            method=SendMessage(chat_id=2, text="Профиль не заполнен"),
            message=description,
        ),
    )


async def test_blocked_user_error_does_not_send_another_reply(caplog):
    # После блокировки бот не отвечает повторно и не пишет о сбое как о
    # необработанной ошибке.
    bot = FakeBot()
    event = make_forbidden_event(
        bot,
        "Forbidden: bot was blocked by the user",
        update_id=10,
    )

    with caplog.at_level(logging.INFO):
        await errors_router.error.trigger(event)

    assert bot.sent_methods == []
    assert "User blocked the bot; update_id=10" in caplog.text
    assert "Unhandled exceptions" not in caplog.text


async def test_other_forbidden_error_uses_global_handler(caplog):
    # Другую ошибку Forbidden обрабатываем как общий сбой
    # и отвечаем на callback.
    bot = FakeBot()
    event = make_forbidden_event(
        bot,
        "Forbidden: bot was kicked from the chat",
        update_id=11,
    )

    with caplog.at_level(logging.ERROR):
        await errors_router.error.trigger(event)

    assert len(bot.sent_methods) == 1
    answer = bot.sent_methods[0]
    assert isinstance(answer, AnswerCallbackQuery)
    assert answer.text == error_callback_message()
    assert answer.show_alert is True
    assert "Unhandled exceptions" in caplog.text


async def test_blocked_user_during_callback_stops_further_replies(
    bot_client: BotClient,
    fake_proposal_service: FakeProjectProposalRequestService,
    caplog,
):
    # Блокировка при отправке сообщения прерывает обработку кнопки без
    # повторных ответов пользователю и лога необработанной ошибки.
    fake_proposal_service.error = UserFreelancerProfileNotFoundError()
    project_id = uuid7()
    bot_client.bot.set_method_error(
        SendMessage,
        lambda method: TelegramForbiddenError(
            method=method,
            message="Forbidden: bot was blocked by the user",
        ),
    )

    with caplog.at_level(logging.INFO):
        await bot_client.click(
            GenerateProposalCB(project_id=project_id).pack(),
        )

    assert fake_proposal_service.requested_project_ids == [project_id]
    assert len(bot_client.bot.sent_methods) == 1
    sent_message = bot_client.bot.get_last_method(SendMessage)
    assert sent_message.chat_id == bot_client.chat_id
    assert sent_message.text == profile_not_set_message()
    assert not any(
        isinstance(method, AnswerCallbackQuery)
        for method in bot_client.bot.sent_methods
    )
    assert (
        f"User blocked the bot; update_id={bot_client.last_update_id}"
        in caplog.text
    )
    assert "Unhandled exceptions" not in caplog.text
    assert "Failed to notify user" not in caplog.text
