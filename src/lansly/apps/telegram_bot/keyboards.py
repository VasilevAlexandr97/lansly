from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lansly.preferences.consts import PRICE_FILTER_PRESETS
from lansly.preferences.dto import (
    CategoryWithFollowedStatusDTO,
    DirectionWithFollowCountsDTO,
)
from lansly.projects.consts import MARKETPLACE_LABELS, Marketplace
from lansly.projects.dto import ProjectLinks
from lansly.projects.models import Project, ProjectCategory
from lansly.subscriptions.models import PlanSlug


class OnboardingAction(StrEnum):
    MARKETPLACE = "marketplace"
    DIRECTION = "direction"
    CATEGORY = "category"
    BACK_TO_MARKETPLACES = "marketplaces"
    BACK_TO_DIRECTIONS = "directions"


class OnboardingCB(CallbackData, prefix="onboarding"):
    action: OnboardingAction
    marketplace: Marketplace | None = None
    category_id: UUID | None = None


class MainMenuCB(CallbackData, prefix="main_menu"):
    delete_message: bool = False


class CategorySettingsAction(StrEnum):
    OPEN = "open"
    MARKETPLACE = "marketplace"
    DIRECTION = "direction"
    TOGGLE = "toggle"
    BACK_TO_MARKETPLACES = "marketplaces"
    BACK_TO_DIRECTIONS = "directions"
    DISABLE_ALL = "disable"
    CONFIRM_DISABLE_ALL = "confirm_disable"


class CategorySettingsCB(CallbackData, prefix="cat_settings"):
    action: CategorySettingsAction
    marketplace: Marketplace | None = None
    category_id: UUID | None = None


class GenerateProposalCB(CallbackData, prefix="gen_proposal"):
    project_id: UUID


class PresetPriceFilterCB(CallbackData, prefix="set_pf"):
    min_price: int
    max_price: int


def build_onboarding_marketplaces_kbd() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for marketplace in Marketplace:
        builder.button(
            text=f"🏪 {MARKETPLACE_LABELS[marketplace]}",
            callback_data=OnboardingCB(
                action=OnboardingAction.MARKETPLACE,
                marketplace=marketplace,
            ).pack(),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_onboarding_directions_kbd(categories: list[ProjectCategory]):
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=category.title,
                callback_data=OnboardingCB(
                    action=OnboardingAction.DIRECTION,
                    category_id=category.id,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Выбрать другую биржу",
            callback_data=OnboardingCB(
                action=OnboardingAction.BACK_TO_MARKETPLACES,
            ).pack(),
        ),
    )
    return builder.as_markup()


def build_onboarding_categories_kbd(categories: list[ProjectCategory]):
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=category.title,
                callback_data=OnboardingCB(
                    action=OnboardingAction.CATEGORY,
                    category_id=category.id,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Выбрать другое направление",
            callback_data=OnboardingCB(
                action=OnboardingAction.BACK_TO_DIRECTIONS,
            ).pack(),
        ),
    )
    return builder.as_markup()


def build_main_menu_kbd(is_pro: bool = False, is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📂 Источники и категории",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.OPEN,
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🛑 Стоп слова",
            callback_data="stop_words_menu",
        ),
        InlineKeyboardButton(
            text="💰 Фильтр цен",
            callback_data="price_filter_menu",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 Профиль",
            callback_data="profile",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="ℹ️ О проекте",
            callback_data="about_project",
        ),
    )
    if not is_admin:
        if is_pro:
            builder.row(
                InlineKeyboardButton(
                    text="👑 Управление подпиской",
                    callback_data="manage_subscription",
                ),
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="👑 PRO подписка",
                    callback_data="pro_subscription",
                ),
            )
    return builder.as_markup()


def build_category_settings_marketplaces_kbd() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for marketplace in Marketplace:
        builder.button(
            text=f"🏪 {MARKETPLACE_LABELS[marketplace]}",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.MARKETPLACE,
                marketplace=marketplace,
            ).pack(),
        )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Отключить мониторинг",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.DISABLE_ALL,
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def build_category_settings_directions_kbd(
    directions: list[DirectionWithFollowCountsDTO],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for direction in directions:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{direction.title}"
                    f"[{direction.followed_count}/{direction.total_count}]"
                ),
                callback_data=CategorySettingsCB(
                    action=CategorySettingsAction.DIRECTION,
                    category_id=direction.id,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К источникам",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.BACK_TO_MARKETPLACES,
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_category_settings_categories_kbd(
    categories: list[CategoryWithFollowedStatusDTO],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in categories:
        category = item.category
        status = "✅" if item.is_followed else "⬜️"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {category.title}",
                callback_data=CategorySettingsCB(
                    action=CategorySettingsAction.TOGGLE,
                    category_id=category.id,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К направлениям",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.BACK_TO_DIRECTIONS,
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_category_settings_disable_confirmation_kbd() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🗑 Отключить",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.CONFIRM_DISABLE_ALL,
            ).pack(),
        ),
        InlineKeyboardButton(
            text="⬅️ Отмена",
            callback_data=CategorySettingsCB(
                action=CategorySettingsAction.BACK_TO_MARKETPLACES,
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_profile_menu_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Редактировать",
            callback_data="edit_profile",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_edit_profile_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data="cancel_edit_profile",
        ),
    )
    return builder.as_markup()


def build_stop_words_menu_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить",
            callback_data="add_stop_words",
        ),
        InlineKeyboardButton(
            text="➖ Удалить",
            callback_data="delete_stop_words",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_start_add_stop_words_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data="cancel_add_stop_words",
        ),
    )
    return builder.as_markup()


def build_start_delete_stop_words_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data="cancel_delete_stop_words",
        ),
    )
    return builder.as_markup()


def build_price_filter_menu_kbd(with_clear: bool = False):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="✏️ Установить",
            callback_data="set_price_filter",
        ),
    )
    if with_clear:
        builder.add(
            InlineKeyboardButton(
                text="🗑 Сбросить",
                callback_data="clear_price_filter",
            ),
        )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def _format_price_preset(min_price: int, max_price: int) -> str:
    return (
        "-".join(f"{p:,}".replace(",", " ") for p in (min_price, max_price))
        + "₽"
    )


def build_start_set_price_filter_kbd() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for min_price, max_price in PRICE_FILTER_PRESETS:
        builder.row(
            InlineKeyboardButton(
                text=_format_price_preset(min_price, max_price),
                callback_data=PresetPriceFilterCB(
                    min_price=min_price,
                    max_price=max_price,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data="cancel_set_price_filter",
        ),
    )
    return builder.as_markup()


def build_project_kbd(project: Project, links: ProjectLinks):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✍️ Сгенерировать отклик",
            callback_data=GenerateProposalCB(project_id=project.id).pack(),
        ),
    )
    if links.customer_url is not None:
        builder.row(
            InlineKeyboardButton(text="👤 Заказчик", url=links.customer_url),
        )
    builder.row(InlineKeyboardButton(text="🔗 Проект", url=links.project_url))
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=False).pack(),
        ),
    )
    return builder.as_markup()


def build_channel_project_kbd(links: ProjectLinks):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔗 Проект",
            url=links.project_url,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🚀 Больше проектов",
            url="https://t.me/lansly_bot?start=source_pr_channel",
        ),
    )
    return builder.as_markup()


def build_subscription_plan_kbd(slug: str, price: Decimal):
    builder = InlineKeyboardBuilder()
    if slug == PlanSlug.PRO_INITIAL:
        text = f"👑 Попробовать PRO за {price:.0f}₽"
    else:
        text = f"👑 PRO за {price:.0f}₽/мес"
    builder.row(
        InlineKeyboardButton(
            text=text,
            callback_data="create_payment",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_payment_kbd(link: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Оплатить",
            url=link,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_payment_email_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_subscription_activated_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_subscription_exists_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👑 Управление подпиской",
            callback_data="manage_subscription",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_no_active_subscription_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👑 PRO подписка",
            callback_data="pro_subscription",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_subscription_manage_kbd(is_cancelled: bool = False):
    builder = InlineKeyboardBuilder()
    if not is_cancelled:
        builder.row(
            InlineKeyboardButton(
                text="❌ Отменить подписку",
                callback_data="cancel_subscription",
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_subscription_cancelled_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_try_again_later_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=True).pack(),
        ),
    )
    return builder.as_markup()


def build_about_project_kbd():
    # TODO: хардкод ссылок
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📢 Канал",
            url="https://t.me/freelance_pr_feed",
        ),
        InlineKeyboardButton(
            text="🌐 Сайт",
            url="https://lansly.ru",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🆘 Поддержка",
            url="https://t.me/askanonagent",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=False).pack(),
        ),
    )
    return builder.as_markup()
