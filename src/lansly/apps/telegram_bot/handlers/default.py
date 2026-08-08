from aiogram import F, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from dishka.integrations.aiogram import FromDishka, inject

from lansly.apps.telegram_bot.keyboards import (
    MainMenuCB,
    build_about_project_kbd,
    build_main_menu_kbd,
    build_start_kbd,
)
from lansly.apps.telegram_bot.messages import (
    about_project_message,
    menu_message,
    start_message,
)
from lansly.auth.telegram_auth import TelegramAuth
from lansly.common.dto import CurrentUser
from lansly.preferences.services import UserCategoryFollowService

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(
    F.message.chat.type == ChatType.PRIVATE,
)


@router.message(CommandStart())
@inject
async def start_handler(
    message: types.Message,
    auth: FromDishka[TelegramAuth],
    service: FromDishka[UserCategoryFollowService],
    state: FSMContext,
):
    if message.from_user is None:
        return
    result = await auth.auth()
    if result.is_new:
        text = start_message()
        keyboard = build_start_kbd()
    else:
        categories = await service.get_followed_categories()
        text = menu_message(categories)
        keyboard = build_main_menu_kbd(
            is_pro=result.is_pro,
            is_admin=result.is_admin,
        )
    await message.answer(
        text,
        reply_markup=keyboard,
    )
    await state.clear()


@router.message(F.text, Command("menu"))
@inject
async def main_menu_command_handler(
    message: types.Message,
    service: FromDishka[UserCategoryFollowService],
    current_user: FromDishka[CurrentUser],
    state: FSMContext,
):
    categories = await service.get_followed_categories()
    text = menu_message(categories)
    keyboard = build_main_menu_kbd(
        is_pro=current_user.is_pro,
        is_admin=current_user.is_admin,
    )
    await message.answer(text, reply_markup=keyboard)
    await state.clear()


@router.callback_query(MainMenuCB.filter())
@inject
async def main_menu_cb_handler(
    call: types.CallbackQuery,
    service: FromDishka[UserCategoryFollowService],
    current_user: FromDishka[CurrentUser],
    state: FSMContext,
    callback_data: MainMenuCB,
):
    categories = await service.get_followed_categories()
    text = menu_message(categories)
    keyboard = build_main_menu_kbd(
        is_pro=current_user.is_pro,
        is_admin=current_user.is_admin,
    )
    if callback_data.delete_message:
        await call.message.delete()
    await call.message.answer(text, reply_markup=keyboard)
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "about_project")
async def about_project_handler(
    call: types.CallbackQuery,
    state: FSMContext,
):
    text = about_project_message()
    keyboard = build_about_project_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.clear()
    await call.answer()
