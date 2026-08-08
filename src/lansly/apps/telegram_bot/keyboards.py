from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lansly.preferences.dto import CategoryWithFollowedStatusDTO
from lansly.projects.models import Project, ProjectCategory
from lansly.subscriptions.models import PlanSlug


class MainMenuCB(CallbackData, prefix="main_menu"):
    delete_message: bool = False


class ManageAction(StrEnum):
    BROWSE_CATEGORIES = "browse_categories"
    BROWSE_SUBCATEGORIES = "browse_subcategories"
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    UNFOLLOW_ALL = "unfollow_all"
    CONFIRM = "confirm"


class ManageFollowedCategoriesCB(CallbackData, prefix="manage_cat"):
    action: ManageAction
    category_id: UUID | None = None


class GenerateProposalCB(CallbackData, prefix="gen_proposal"):
    project_id: UUID


def build_start_kbd() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📂 Категории",
        callback_data="configure_followed_categories",
    )
    return builder.as_markup()


def build_main_menu_kbd(is_pro: bool = False, is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📂 Категории",
            callback_data="configure_followed_categories",
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


def build_followed_categories_kbd(
    categories: list[ProjectCategory],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=category.title,
                callback_data=ManageFollowedCategoriesCB(
                    action=ManageAction.BROWSE_SUBCATEGORIES,
                    category_id=category.id,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отписаться от всех",
            callback_data=ManageFollowedCategoriesCB(
                action=ManageAction.UNFOLLOW_ALL,
                category_id=None,
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


def build_followed_subcategories_kbd(
    categories: list[CategoryWithFollowedStatusDTO],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        status = "✅" if category.is_followed else "⬜️"
        action = (
            ManageAction.FOLLOW
            if not category.is_followed
            else ManageAction.UNFOLLOW
        )
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {category.category.title}",
                callback_data=ManageFollowedCategoriesCB(
                    action=action,
                    category_id=category.category.id,
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data=ManageFollowedCategoriesCB(
                action=ManageAction.BROWSE_CATEGORIES,
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


def build_start_set_price_filter_kbd():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data="cancel_set_price_filter",
        ),
    )
    return builder.as_markup()


def build_project_kbd(project: Project, ref_id: int | None = None):
    project_link = f"https://kwork.ru/projects/{project.external_id}"
    if ref_id is not None:
        project_link += f"?ref={ref_id}"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✍️ Сгенерировать отклик",
            callback_data=GenerateProposalCB(project_id=project.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔗 Проект",
            url=project_link,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏚 Меню",
            callback_data=MainMenuCB(delete_message=False).pack(),
        ),
    )
    return builder.as_markup()


def build_channel_project_kbd(project: Project, ref_id: int | None = None):
    project_link = f"https://kwork.ru/projects/{project.external_id}"
    if ref_id is not None:
        project_link += f"?ref={ref_id}"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔗 Проект",
            url=project_link,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🚀 Больше проектов",
            url="https://t.me/lansly_bot",
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
