# ruff: noqa: PLR2004
from uuid import uuid7

import pytest

from fakes.factories import category, project

from lansly.apps.telegram_bot import keyboards as k
from lansly.preferences.dto import (
    CategoryWithFollowedStatusDTO as Status,
    DirectionWithFollowCountsDTO as Direction,
)
from lansly.projects.dto import ProjectLinks


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_onboarding_marketplaces():
    # Проверяет названия и порядок кнопок Kwork и FL.ru, а также значения
    # площадок в callback онбординга.
    bs = flat(k.build_onboarding_marketplaces_kbd())
    assert [b.text for b in bs] == ["🏪 KWORK", "🏪 FL"]
    assert [
        k.OnboardingCB.unpack(b.callback_data).marketplace for b in bs
    ] == ["kwork", "fl"]


def test_onboarding_directions():
    # Проверяет название и ID направления в кнопке онбординга и действие
    # возврата к площадкам.
    c = category()
    bs = flat(k.build_onboarding_directions_kbd([c]))
    assert bs[0].text == c.title
    assert k.OnboardingCB.unpack(bs[0].callback_data).category_id == c.id
    assert (
        k.OnboardingCB.unpack(bs[-1].callback_data).action
        == k.OnboardingAction.BACK_TO_MARKETPLACES
    )


def test_onboarding_categories():
    # Проверяет действие выбора категории, её ID в callback и кнопку возврата к
    # направлениям.
    c = category()
    bs = flat(k.build_onboarding_categories_kbd([c]))
    assert (
        k.OnboardingCB.unpack(bs[0].callback_data).action
        == k.OnboardingAction.CATEGORY
    )
    assert k.OnboardingCB.unpack(bs[0].callback_data).category_id == c.id
    assert (
        k.OnboardingCB.unpack(bs[-1].callback_data).action
        == k.OnboardingAction.BACK_TO_DIRECTIONS
    )


@pytest.mark.parametrize(
    "builder",
    [k.build_onboarding_directions_kbd, k.build_onboarding_categories_kbd],
)
def test_onboarding_empty_lists(builder):
    # Проверяет, что пустые списки направлений и категорий оставляют в
    # онбординге одну кнопку.
    assert len(flat(builder([]))) == 1


@pytest.mark.parametrize("action", list(k.OnboardingAction))
def test_onboarding_callback_roundtrip(action):
    # Проверяет обратимость упаковки callback для каждого действия онбординга и
    # соблюдение лимита 64 байта.
    # Только поля данного действия: callback не должен превышать 64 байта.
    data = k.OnboardingCB(
        action=action,
        marketplace="fl" if action == k.OnboardingAction.MARKETPLACE else None,
        category_id=uuid7()
        if action
        in (k.OnboardingAction.DIRECTION, k.OnboardingAction.CATEGORY)
        else None,
    )
    assert k.OnboardingCB.unpack(data.pack()) == data
    assert len(data.pack().encode()) <= 64


def test_settings_marketplaces():
    # Проверяет кнопки обеих площадок, отключения мониторинга и перехода в меню
    # с удалением сообщения в настройках.
    bs = flat(k.build_category_settings_marketplaces_kbd())
    assert [
        k.CategorySettingsCB.unpack(b.callback_data).marketplace
        for b in bs[:2]
    ] == ["kwork", "fl"]
    assert (
        k.CategorySettingsCB.unpack(bs[2].callback_data).action
        == k.CategorySettingsAction.DISABLE_ALL
    )
    assert k.MainMenuCB.unpack(bs[-1].callback_data).delete_message


@pytest.mark.parametrize(
    ("followed", "total"),
    [(0, 0), (0, 4), (2, 4), (4, 4)],
)
def test_settings_direction_counts(followed, total):
    # Проверяет показ числа выбранных и доступных категорий в названии кнопки
    # направления и передачу его ID.
    c = Direction(uuid7(), "Дизайн", followed, total)
    b = flat(k.build_category_settings_directions_kbd([c]))[0]
    assert b.text == f"Дизайн[{followed}/{total}]"
    assert k.CategorySettingsCB.unpack(b.callback_data).category_id == c.id


@pytest.mark.parametrize(("active", "marker"), [(True, "✅"), (False, "⬜️")])
def test_settings_category_status(active, marker):
    # Проверяет отметку активности категории и callback переключения с её ID в
    # клавиатуре настроек.
    c = category()
    b = flat(k.build_category_settings_categories_kbd([Status(c, active)]))[0]
    assert b.text == f"{marker} {c.title}"
    data = k.CategorySettingsCB.unpack(b.callback_data)
    assert data.category_id == c.id
    assert data.action == k.CategorySettingsAction.TOGGLE


def test_settings_navigation():
    # Проверяет действия возврата к предыдущему шагу и перехода в меню с
    # удалением сообщения в настройках.
    for builder, action in [
        (
            k.build_category_settings_directions_kbd,
            k.CategorySettingsAction.BACK_TO_MARKETPLACES,
        ),
        (
            k.build_category_settings_categories_kbd,
            k.CategorySettingsAction.BACK_TO_DIRECTIONS,
        ),
    ]:
        bs = flat(builder([]))
        assert (
            k.CategorySettingsCB.unpack(bs[-2].callback_data).action == action
        )
        assert k.MainMenuCB.unpack(bs[-1].callback_data).delete_message


@pytest.mark.parametrize(
    "builder",
    [
        k.build_category_settings_directions_kbd,
        k.build_category_settings_categories_kbd,
    ],
)
def test_settings_empty_lists(builder):
    # Проверяет, что пустые списки направлений и категорий оставляют в
    # настройках две кнопки.
    assert len(flat(builder([]))) == 2


def test_settings_disable_confirmation():
    # Проверяет кнопки подтверждения отключения, возврата к площадкам и
    # перехода в меню с удалением сообщения.
    bs = flat(k.build_category_settings_disable_confirmation_kbd())
    assert [
        k.CategorySettingsCB.unpack(b.callback_data).action for b in bs[:2]
    ] == [
        k.CategorySettingsAction.CONFIRM_DISABLE_ALL,
        k.CategorySettingsAction.BACK_TO_MARKETPLACES,
    ]
    assert k.MainMenuCB.unpack(bs[-1].callback_data).delete_message


@pytest.mark.parametrize("action", list(k.CategorySettingsAction))
def test_settings_callback_roundtrip(action):
    # Проверяет обратимость упаковки callback для каждого действия настроек и
    # соблюдение лимита 64 байта.
    data = k.CategorySettingsCB(
        action=action,
        marketplace="fl"
        if action == k.CategorySettingsAction.MARKETPLACE
        else None,
        category_id=uuid7()
        if action
        in (
            k.CategorySettingsAction.DIRECTION,
            k.CategorySettingsAction.TOGGLE,
        )
        else None,
    )
    assert k.CategorySettingsCB.unpack(data.pack()) == data
    assert len(data.pack().encode()) <= 64


def test_main_menu_settings_entry():
    # Проверяет, что первый пункт главного меню открывает настройки источников
    # и категорий.
    first = flat(k.build_main_menu_kbd())[0]
    assert first.text == "📂 Источники и категории"
    assert (
        k.CategorySettingsCB.unpack(first.callback_data).action
        == k.CategorySettingsAction.OPEN
    )


@pytest.mark.parametrize(
    ("pro", "admin", "expected"),
    [
        (False, False, "pro_subscription"),
        (True, False, "manage_subscription"),
        (False, True, None),
        (True, True, None),
    ],
)
def test_main_menu_subscription_roles(pro, admin, expected):
    # Проверяет выбор кнопки покупки или управления подпиской для FREE и PRO и
    # отсутствие этих кнопок у администратора.
    data = {b.callback_data for b in flat(k.build_main_menu_kbd(pro, admin))}
    assert (
        (expected in data)
        if expected
        else not data & {"pro_subscription", "manage_subscription"}
    )


@pytest.mark.parametrize("url", [None, "https://kwork.ru/user/alice"])
def test_project_customer_link(url):
    # Проверяет добавление ссылки на заказчика только при её наличии с
    # сохранением ссылки на проект.
    urls = [
        b.url
        for b in flat(
            k.build_project_kbd(
                project(),
                ProjectLinks("https://fl.ru/projects/42/", url),
            ),
        )
        if b.url
    ]
    assert urls == ([url] if url else []) + ["https://fl.ru/projects/42/"]


def test_project_links_and_generation():
    # Проверяет ID проекта в кнопке генерации отклика, ссылку на проект и
    # переход в меню без удаления сообщения.
    p = project()
    bs = flat(
        k.build_project_kbd(p, ProjectLinks("https://fl.ru/projects/42/")),
    )
    assert k.GenerateProposalCB.unpack(bs[0].callback_data).project_id == p.id
    assert bs[1].url == "https://fl.ru/projects/42/"
    assert not k.MainMenuCB.unpack(bs[-1].callback_data).delete_message


def test_channel_project_links():
    # Проверяет ссылки на проект и запуск бота с источником pr_channel в
    # клавиатуре канального уведомления.
    bs = flat(
        k.build_channel_project_kbd(
            ProjectLinks("https://fl.ru/projects/42/"),
        ),
    )
    assert [b.url for b in bs] == [
        "https://fl.ru/projects/42/",
        "https://t.me/lansly_bot?start=source_pr_channel",
    ]
