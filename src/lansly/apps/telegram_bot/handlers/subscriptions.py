import contextlib
import logging

from aiogram import F, Router, types
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from dishka.integrations.aiogram import FromDishka, inject

from lansly.apps.telegram_bot.keyboards import (
    build_no_active_subscription_kbd,
    build_payment_email_kbd,
    build_payment_kbd,
    build_subscription_cancelled_kbd,
    build_subscription_exists_kbd,
    build_subscription_manage_kbd,
    build_subscription_plan_kbd,
    build_try_again_later_kbd,
)
from lansly.apps.telegram_bot.messages import (
    not_active_subscription_message,
    payment_email_message,
    payment_email_validation_error_message,
    payment_message,
    pro_subscription_info_message,
    subscription_already_cancelled_message,
    subscription_cancelled_message,
    subscription_exists_message,
    subscription_info_message,
    try_again_later_message,
)
from lansly.apps.telegram_bot.states import PaymentState
from lansly.subscriptions.exceptions import (
    ActiveSubscriptionExistsError,
    PaymentAlreadyPaidError,
    PaymentEmailRequiredError,
    PaymentEmailValidationError,
    SubscriptionAlreadyCancelledError,
)
from lansly.subscriptions.services import (
    SubscriptionManagementService,
    SubscriptionPaymentService,
)

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(
    F.message.chat.type == ChatType.PRIVATE,
)


@router.callback_query(F.data == "pro_subscription")
@inject
async def pro_subscription_info(
    call: types.CallbackQuery,
    service: FromDishka[SubscriptionPaymentService],
):
    try:
        plan = await service.get_plan_for_user()
        text = pro_subscription_info_message(
            plan_slug=plan.slug,
            price=plan.price,
            monthly_price=plan.monthly_price,
            duration_days=plan.duration_days,
        )
        keyboard = build_subscription_plan_kbd(
            slug=plan.slug,
            price=plan.price,
        )
    except ActiveSubscriptionExistsError:
        text = subscription_exists_message()
        keyboard = build_subscription_exists_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "create_payment")
@inject
async def create_payment(
    call: types.CallbackQuery,
    service: FromDishka[SubscriptionPaymentService],
    state: FSMContext,
):
    try:
        payment = await service.get_or_create_pending_payment()
        text = payment_message(
            payment_id=payment.yookassa_payment_id,
            email=payment.email,
            amount=payment.amount,
            link=payment.link,
        )
        keyboard = build_payment_kbd(payment.link)
    except PaymentEmailRequiredError:
        text = payment_email_message()
        keyboard = build_payment_email_kbd()
        await state.set_state(PaymentState.set_email)
    except ActiveSubscriptionExistsError:
        text = subscription_exists_message()
        keyboard = build_subscription_exists_kbd()
    except PaymentAlreadyPaidError:
        text = try_again_later_message()
        keyboard = build_try_again_later_kbd()
    with contextlib.suppress(TelegramBadRequest):
        await call.message.edit_text(text, reply_markup=keyboard)


@router.message(PaymentState.set_email, F.text)
@inject
async def set_payment_email(
    message: types.Message,
    service: FromDishka[SubscriptionPaymentService],
    state: FSMContext,
):
    state_clear = False
    try:
        email = message.text
        payment = await service.get_or_create_pending_payment(email)
        text = payment_message(
            payment_id=payment.yookassa_payment_id,
            email=payment.email,
            amount=payment.amount,
            link=payment.link,
        )
        keyboard = build_payment_kbd(payment.link)
        state_clear = True
    except PaymentEmailValidationError:
        text = payment_email_validation_error_message()
        keyboard = build_payment_email_kbd()
    except ActiveSubscriptionExistsError:
        text = subscription_exists_message()
        keyboard = build_subscription_exists_kbd()
    except PaymentAlreadyPaidError:
        text = try_again_later_message()
        keyboard = build_try_again_later_kbd()
    await message.answer(text, reply_markup=keyboard)
    if state_clear:
        await state.clear()


@router.callback_query(F.data == "manage_subscription")
@inject
async def manage_subscription(
    call: types.CallbackQuery,
    service: FromDishka[SubscriptionManagementService],
):
    info = await service.get_active_subscription_info()
    if info:
        text = subscription_info_message(info)
        keyboard = build_subscription_manage_kbd(
            is_cancelled=info.is_cancelled,
        )
    else:
        text = not_active_subscription_message()
        keyboard = build_no_active_subscription_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "cancel_subscription")
@inject
async def cancel_subscription(
    call: types.CallbackQuery,
    service: FromDishka[SubscriptionManagementService],
):
    try:
        subscription = await service.cancel_subscription()
        text = subscription_cancelled_message(subscription.expires_at)
    except SubscriptionAlreadyCancelledError:
        text = subscription_already_cancelled_message()
    keyboard = build_subscription_cancelled_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)
