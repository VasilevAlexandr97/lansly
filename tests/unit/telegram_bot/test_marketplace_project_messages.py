# ruff: noqa: PLR2004
import pytest

from fakes.factories import customer, project

from lansly.apps.telegram_bot.messages import (
    flru_project_message,
    kwork_project_message,
    truncate_project_description,
)
from lansly.projects.dto import ProjectLinks

LINKS = ProjectLinks(
    "https://example.test/project",
    "https://example.test/customer",
)


def test_kwork_project_template():
    # Проверяет наличие площадки Kwork, категории, описания, обеих границ
    # бюджета, хештега и ссылки в сообщении проекта.
    text = kwork_project_message(project(source="kwork"), LINKS)
    for fragment in [
        "KWORK",
        "Дизайн",
        "Нарисовать логотип",
        "30000",
        "40000",
        "#дизайн",
        LINKS.project_url,
    ]:
        assert fragment in text


def test_kwork_customer_block():
    # Проверяет включение имени, статистики и ссылки на заказчика в сообщение
    # проекта Kwork.
    text = kwork_project_message(project(customer=customer()), LINKS)
    for fragment in ["alice", "12", "75%", LINKS.customer_url]:
        assert fragment in text


def test_kwork_without_customer():
    # Проверяет отсутствие блока заказчика в сообщении Kwork, если у проекта
    # нет заказчика.
    assert "Заказчик" not in kwork_project_message(project(), LINKS)


@pytest.mark.parametrize("price", [0, 30000])
def test_fl_exact_budget(price):
    # Проверяет показ точного бюджета FL.ru, включая нулевой, без пометки о
    # договорной цене.
    text = flru_project_message(
        project(price=price, has_exact_budget=True),
        LINKS,
    )
    assert f"Бюджет: {price} ₽" in text
    assert "по договорённости" not in text


def test_fl_negotiable_budget():
    # Проверяет показ пометки о договорном бюджете FL.ru вместо числовой цены
    # при has_exact_budget=False.
    text = flru_project_message(
        project(price=123, has_exact_budget=False),
        LINKS,
    )
    assert "по договорённости" in text
    assert "123 ₽" not in text


def test_fl_project_template():
    # Проверяет основные данные и ссылку проекта FL.ru в сообщении при
    # отсутствии блока и ссылки заказчика.
    text = flru_project_message(project(customer=customer()), LINKS)
    for fragment in [
        "FL",
        "Дизайн",
        "Нарисовать логотип",
        "#дизайн",
        LINKS.project_url,
    ]:
        assert fragment in text
    assert "Заказчик" not in text
    assert LINKS.customer_url not in text


@pytest.mark.parametrize("length", [2999, 3000, 3001])
def test_description_truncation_boundaries(length):
    # Проверяет обрезку описания до 3000 символов с многоточием только при
    # превышении лимита.
    text = "я" * length
    assert truncate_project_description(text) == (
        "я" * min(length, 3000) + ("..." if length > 3000 else "")
    )


def test_description_custom_limit():
    # Проверяет обрезку описания по заданному лимиту и сохранение пустой
    # строки.
    assert truncate_project_description("abcdef", 3) == "abc..."
    assert truncate_project_description("", 3) == ""


@pytest.mark.parametrize(
    "builder",
    [kwork_project_message, flru_project_message],
)
def test_both_templates_truncate(builder):
    # Проверяет обрезку длинного описания с многоточием в шаблонах обеих
    # площадок.
    text = builder(project(description="я" * 3001), LINKS)
    assert "я" * 3000 + "..." in text
    assert "я" * 3001 not in text


@pytest.mark.parametrize(
    "builder",
    [kwork_project_message, flru_project_message],
)
def test_description_line_breaks(builder):
    # Проверяет сохранение переносов между абзацами описания в шаблонах обеих
    # площадок.
    text = "Первый абзац\n\nВторой абзац"
    assert text in builder(project(description=text), LINKS)
