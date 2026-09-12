import pytest

from lansly.apps.telegram_bot import messages as m
from lansly.preferences.dto import SourceCategoryFollowCountDTO as Count


def test_onboarding_welcome():
    # Проверяет упоминание обеих площадок и предложение выбрать биржу в
    # приветствии онбординга.
    text = m.onboarding_start_message()
    assert "kwork.ru" in text
    assert "fl.ru" in text
    assert "выберите биржу" in text


@pytest.mark.parametrize(
    ("source", "label"),
    [("fl", "FL"), ("kwork", "KWORK")],
)
def test_onboarding_direction(source, label):
    # Проверяет название выбранной площадки и номер первого шага в сообщении
    # выбора направления.
    text = m.onboarding_select_direction_message(source)
    assert label in text
    assert "Шаг 1 из 2" in text


def test_onboarding_category():
    # Проверяет название площадки, номер второго шага и HTML-экранирование
    # названия направления при выборе категории.
    text = m.onboarding_select_category_message("fl", "<Лого> & Web")
    assert "FL" in text
    assert "Шаг 2 из 2" in text
    assert "&lt;Лого&gt; &amp; Web" in text


def test_onboarding_complete():
    # Проверяет название площадки, HTML-экранирование категории и сообщение о
    # запуске мониторинга после онбординга.
    text = m.onboarding_complete_message("kwork", "<Лого>")
    assert "KWORK" in text
    assert "&lt;Лого&gt;" in text
    assert "Мониторинг запущен" in text


def test_menu_source_counts():
    # Проверяет отображение отдельных счётчиков подписок Kwork и FL.ru в
    # главном меню.
    text = m.menu_message([Count("kwork", 3), Count("fl", 2)])
    assert "KWORK - 3" in text
    assert "FL - 2" in text


@pytest.mark.parametrize("counts", [[], [Count("fl", 0), Count("kwork", 0)]])
def test_menu_no_follows(counts):
    # Проверяет предложение выбрать категории при пустом списке счётчиков или
    # нулевых подписках на обеих площадках.
    assert "Выберите категории" in m.menu_message(counts)


def test_menu_one_active_source():
    # Проверяет показ счётчика активной площадки и пометки «не настроено» у
    # площадки без подписок.
    text = m.menu_message([Count("kwork", 1), Count("fl", 0)])
    assert "KWORK - 1" in text
    assert "FL - не настроено" in text


@pytest.mark.parametrize(
    ("source", "label"),
    [("fl", "FL"), ("kwork", "KWORK")],
)
def test_settings_messages(source, label):
    # Проверяет наличие сообщения выбора площадки и её названия в сообщениях
    # выбора направления и категории настроек.
    assert m.category_settings_select_marketplace_message()
    assert label in m.category_settings_select_direction_message(source)
    assert label in m.category_settings_select_category_message(source, "Web")


def test_settings_direction_escaping():
    # Проверяет HTML-экранирование названия направления в сообщении выбора
    # категории настроек.
    assert (
        "&lt;Web&gt; &amp; API"
        in m.category_settings_select_category_message("fl", "<Web> & API")
    )


def test_settings_disable_messages():
    # Проверяет упоминание отключения в запросе подтверждения и сообщении о
    # завершённом отключении мониторинга.
    assert (
        "отключить"
        in m.category_settings_disable_confirmation_message().lower()
    )
    assert "отключ" in m.category_settings_disabled_message().lower()


@pytest.mark.parametrize("limit", [1, 9999])
def test_category_limit_message(limit):
    # Проверяет включение переданного лимита категорий в сообщение о его
    # превышении.
    assert str(limit) in m.categories_limit_exceeded_message(limit)


def test_expired_setup_message():
    # Проверяет, что сообщение об устаревшей настройке непустое и указывает на
    # истечение её срока.
    text = m.monitoring_setup_expired_message()
    assert text
    assert "устар" in text.lower() or "истек" in text.lower()
