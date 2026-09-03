from aiogram import F, Router, types
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from dishka.integrations.aiogram import FromDishka, inject

from lansly.apps.telegram_bot.keyboards import (
    OnboardingAction,
    OnboardingCB,
    build_main_menu_kbd,
    build_onboarding_categories_kbd,
    build_onboarding_directions_kbd,
    build_onboarding_marketplaces_kbd,
)
from lansly.apps.telegram_bot.messages import (
    categories_limit_exceeded_message,
    category_selection_expired_message,
    onboarding_complete_message,
    onboarding_select_category_message,
    onboarding_select_direction_message,
    onboarding_start_message,
)
from lansly.apps.telegram_bot.states import OnboardingState
from lansly.common.dto import CurrentUser
from lansly.preferences.exceptions import UserCategoryFollowLimitExceededError
from lansly.preferences.services import UserCategoryFollowService
from lansly.projects.services import ProjectCategoryService

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(
    F.message.chat.type == ChatType.PRIVATE,
)


@router.callback_query(
    OnboardingState.select_direction,
    OnboardingCB.filter(F.action == OnboardingAction.BACK_TO_MARKETPLACES),
)
async def back_to_marketplaces_handler(
    call: types.CallbackQuery,
    state: FSMContext,
):
    if not isinstance(call.message, types.Message):
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    text = onboarding_start_message()
    keyboard = build_onboarding_marketplaces_kbd()
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(OnboardingState.select_marketplace)
    await call.answer()


@router.callback_query(
    OnboardingState.select_category,
    OnboardingCB.filter(F.action == OnboardingAction.BACK_TO_DIRECTIONS),
)
@inject
async def back_to_directions_handler(
    call: types.CallbackQuery,
    service: FromDishka[ProjectCategoryService],
    state: FSMContext,
):
    marketplace = await state.get_value("marketplace")
    if marketplace is None or not isinstance(call.message, types.Message):
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    root_categories = await service.get_root_categories(marketplace)
    await state.update_data(
        marketplace=marketplace,
        directions={str(c.id): c.title for c in root_categories},
    )
    text = onboarding_select_direction_message(marketplace)
    keyboard = build_onboarding_directions_kbd(root_categories)
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(OnboardingState.select_direction)
    await call.answer()


@router.callback_query(
    OnboardingState.select_marketplace,
    OnboardingCB.filter(
        (F.action == OnboardingAction.MARKETPLACE)
        & (F.marketplace.is_not(None)),
    ),
)
@inject
async def select_marketplace_handler(
    call: types.CallbackQuery,
    service: FromDishka[ProjectCategoryService],
    callback_data: OnboardingCB,
    state: FSMContext,
):
    marketplace = callback_data.marketplace
    if marketplace is None or not isinstance(call.message, types.Message):
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    root_categories = await service.get_root_categories(marketplace)
    await state.update_data(
        marketplace=marketplace,
        directions={str(c.id): c.title for c in root_categories},
    )
    text = onboarding_select_direction_message(marketplace)
    keyboard = build_onboarding_directions_kbd(root_categories)
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(OnboardingState.select_direction)
    await call.answer()


@router.callback_query(
    OnboardingState.select_direction,
    OnboardingCB.filter(
        (F.action == OnboardingAction.DIRECTION)
        & (F.category_id.is_not(None)),
    ),
)
@inject
async def select_direction_handler(
    call: types.CallbackQuery,
    service: FromDishka[ProjectCategoryService],
    callback_data: OnboardingCB,
    state: FSMContext,
):
    direction = callback_data.category_id
    if direction is None or not isinstance(call.message, types.Message):
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    state_data = await state.get_data()
    marketplace = state_data.get("marketplace")
    directions = state_data.get("directions", {})
    direction_name = directions.get(str(direction))
    if marketplace is None or direction_name is None:
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    categories = await service.get_subcategories(direction)
    await state.update_data(
        categories={
            str(category.id): category.title for category in categories
        },
    )
    text = onboarding_select_category_message(
        marketplace=marketplace,
        direction=direction_name,
    )
    keyboard = build_onboarding_categories_kbd(categories)
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(OnboardingState.select_category)
    await call.answer()


@router.callback_query(
    OnboardingState.select_category,
    OnboardingCB.filter(
        (F.action == OnboardingAction.CATEGORY) & (F.category_id.is_not(None)),
    ),
)
@inject
async def select_category_handler(
    call: types.CallbackQuery,
    service: FromDishka[UserCategoryFollowService],
    current_user: FromDishka[CurrentUser],
    callback_data: OnboardingCB,
    state: FSMContext,
):
    category_id = callback_data.category_id
    if category_id is None or not isinstance(call.message, types.Message):
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    state_data = await state.get_data()
    marketplace = state_data.get("marketplace")
    categories = state_data.get("categories", {})
    category_title = categories.get(str(category_id))
    if marketplace is None or category_title is None:
        await call.answer(
            category_selection_expired_message(),
            show_alert=True,
        )
        return
    try:
        followed_category = await service.follow_category(category_id)
    except UserCategoryFollowLimitExceededError as exc:
        await call.answer(
            categories_limit_exceeded_message(exc.limit),
            show_alert=True,
        )
        return
    text = onboarding_complete_message(marketplace, followed_category.title)
    keyboard = build_main_menu_kbd(
        is_pro=current_user.is_pro,
        is_admin=current_user.is_admin,
    )
    await call.message.edit_text(text, reply_markup=keyboard)
    await state.clear()
    await call.answer()


@router.callback_query(OnboardingCB.filter())
async def expired_onboarding_callback_handler(
    call: types.CallbackQuery,
):
    await call.answer(
        category_selection_expired_message(),
        show_alert=True,
    )
