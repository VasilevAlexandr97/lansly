from aiogram import F, Router, types
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from dishka.integrations.aiogram import FromDishka, inject

from lansly.apps.telegram_bot.keyboards import (
    CategorySettingsAction,
    CategorySettingsCB,
    build_category_settings_categories_kbd,
    build_category_settings_directions_kbd,
    build_category_settings_disable_confirmation_kbd,
    build_category_settings_marketplaces_kbd,
    build_main_menu_kbd,
)
from lansly.apps.telegram_bot.messages import (
    categories_limit_exceeded_message,
    category_settings_disable_confirmation_message,
    category_settings_disabled_message,
    category_settings_select_category_message,
    category_settings_select_direction_message,
    category_settings_select_marketplace_message,
    monitoring_setup_expired_message,
)
from lansly.apps.telegram_bot.states import CategorySettingsState
from lansly.common.dto import CurrentUser
from lansly.preferences.exceptions import UserCategoryFollowLimitExceededError
from lansly.preferences.services import UserCategoryFollowService

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(
    F.message.chat.type == ChatType.PRIVATE,
)


@router.callback_query(
    StateFilter(
        CategorySettingsState.select_direction,
        CategorySettingsState.confirm_disable_monitoring,
    ),
    CategorySettingsCB.filter(
        F.action == CategorySettingsAction.BACK_TO_MARKETPLACES,
    ),
)
@inject
async def back_to_marketplaces_handler(
    call: types.CallbackQuery,
    state: FSMContext,
):
    if not isinstance(call.message, types.Message):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    text = category_settings_select_marketplace_message()
    keyboard = build_category_settings_marketplaces_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.clear()
    await state.set_state(CategorySettingsState.select_marketplace)
    await call.answer()


@router.callback_query(
    CategorySettingsState.select_category,
    CategorySettingsCB.filter(
        F.action == CategorySettingsAction.BACK_TO_DIRECTIONS,
    ),
)
@inject
async def back_to_directions_handler(
    call: types.CallbackQuery,
    follow_service: FromDishka[UserCategoryFollowService],
    state: FSMContext,
):
    marketplace = await state.get_value("marketplace")
    if marketplace is None or not isinstance(call.message, types.Message):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    directions = await follow_service.get_directions_with_follow_counts(
        marketplace,
    )
    await state.update_data(
        marketplace=marketplace,
        directions={str(item.id): item.title for item in directions},
    )
    text = category_settings_select_direction_message(marketplace)
    keyboard = build_category_settings_directions_kbd(directions)
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(CategorySettingsState.select_direction)
    await call.answer()


@router.callback_query(
    CategorySettingsCB.filter(F.action == CategorySettingsAction.OPEN),
)
@inject
async def open_category_settings_handler(
    call: types.CallbackQuery,
    state: FSMContext,
):
    if not isinstance(call.message, types.Message):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    text = category_settings_select_marketplace_message()
    keyboard = build_category_settings_marketplaces_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.clear()
    await state.set_state(CategorySettingsState.select_marketplace)
    await call.answer()


@router.callback_query(
    CategorySettingsState.select_marketplace,
    CategorySettingsCB.filter(
        (F.action == CategorySettingsAction.MARKETPLACE)
        & (F.marketplace.is_not(None)),
    ),
)
@inject
async def select_marketplace_handler(
    call: types.CallbackQuery,
    follow_service: FromDishka[UserCategoryFollowService],
    callback_data: CategorySettingsCB,
    state: FSMContext,
):
    marketplace = callback_data.marketplace
    if marketplace is None or not isinstance(call.message, types.Message):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    directions = await follow_service.get_directions_with_follow_counts(
        marketplace,
    )
    await state.update_data(
        marketplace=marketplace,
        directions={str(item.id): item.title for item in directions},
    )
    text = category_settings_select_direction_message(marketplace)
    keyboard = build_category_settings_directions_kbd(directions)
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(CategorySettingsState.select_direction)
    await call.answer()


@router.callback_query(
    CategorySettingsState.select_direction,
    CategorySettingsCB.filter(
        (F.action == CategorySettingsAction.DIRECTION)
        & (F.category_id.is_not(None)),
    ),
)
@inject
async def select_direction_handler(
    call: types.CallbackQuery,
    service: FromDishka[UserCategoryFollowService],
    callback_data: CategorySettingsCB,
    state: FSMContext,
):
    direction_id = callback_data.category_id
    if direction_id is None or not isinstance(call.message, types.Message):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    state_data = await state.get_data()
    marketplace = state_data.get("marketplace")
    directions = state_data.get("directions", {})
    direction_title = directions.get(str(direction_id))
    if marketplace is None or direction_title is None:
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    result = await service.get_subcategories_with_follow_status(direction_id)
    await state.update_data(
        direction_title=direction_title,
        categories={
            str(item.category.id): item.category.title for item in result
        },
    )
    text = category_settings_select_category_message(
        marketplace=marketplace,
        direction=direction_title,
    )
    keyboard = build_category_settings_categories_kbd(result)
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(CategorySettingsState.select_category)
    await call.answer()


@router.callback_query(
    CategorySettingsState.select_category,
    CategorySettingsCB.filter(
        (F.action == CategorySettingsAction.TOGGLE)
        & (F.category_id.is_not(None)),
    ),
)
@inject
async def toggle_category_handler(
    call: types.CallbackQuery,
    service: FromDishka[UserCategoryFollowService],
    callback_data: CategorySettingsCB,
    state: FSMContext,
):
    category_id = callback_data.category_id
    if category_id is None or not isinstance(call.message, types.Message):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    state_data = await state.get_data()
    marketplace = state_data.get("marketplace")
    direction_title = state_data.get("direction_title")
    categories = state_data.get("categories", {})
    if (
        marketplace is None
        or direction_title is None
        or str(category_id) not in categories
    ):
        await call.answer(
            monitoring_setup_expired_message(),
            show_alert=True,
        )
        return
    try:
        result = await service.toggle_category_follow(category_id)
        text = category_settings_select_category_message(
            marketplace=marketplace,
            direction=direction_title,
        )
        keyboard = build_category_settings_categories_kbd(result.categories)
        await call.message.edit_text(text, reply_markup=keyboard)
        await call.answer()
    except UserCategoryFollowLimitExceededError as exc:
        text = categories_limit_exceeded_message(exc.limit)
        await call.answer(text, show_alert=True)


@router.callback_query(
    CategorySettingsState.select_marketplace,
    CategorySettingsCB.filter(F.action == CategorySettingsAction.DISABLE_ALL),
)
async def request_disable_monitoring_handler(
    call: types.CallbackQuery,
    state: FSMContext,
):
    if not isinstance(call.message, types.Message):
        await call.answer()
        return
    text = category_settings_disable_confirmation_message()
    keyboard = build_category_settings_disable_confirmation_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(CategorySettingsState.confirm_disable_monitoring)
    await call.answer()


@router.callback_query(
    CategorySettingsState.confirm_disable_monitoring,
    CategorySettingsCB.filter(
        F.action == CategorySettingsAction.CONFIRM_DISABLE_ALL,
    ),
)
@inject
async def confirm_disable_monitoring_handler(
    call: types.CallbackQuery,
    service: FromDishka[UserCategoryFollowService],
    current_user: FromDishka[CurrentUser],
    state: FSMContext,
):
    if not isinstance(call.message, types.Message):
        await call.answer()
        return
    await service.unfollow_all_categories()
    text = category_settings_disabled_message()
    keyboard = build_main_menu_kbd(
        is_pro=current_user.is_pro,
        is_admin=current_user.is_admin,
    )
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.clear()
    await call.answer()


@router.callback_query(CategorySettingsCB.filter())
async def expired_category_settings_callback_handler(
    call: types.CallbackQuery,
):
    await call.answer(
        monitoring_setup_expired_message(),
        show_alert=True,
    )
