import pytest

from lansly.apps.telegram_bot.messages import make_hashtag


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Скрипты, боты и mini apps", "#скрипты_боты_и_mini_apps"),
        ("Web Design", "#web_design"),
        ("3D Modeling", "#3d_modeling"),
        ("Дизайн", "#дизайн"),
        ("A , B", "#a_b"),
        (" test ", "#test"),
    ],
)
def test_make_hashtag(title, expected):
    # Проверяет преобразование названия в хештег с нижним регистром, удалением
    # запятых и заменой пробелов подчёркиваниями.
    assert make_hashtag(title) == expected


def test_make_hashtag_collapses_multiple_underscores():
    # Проверяет замену нескольких последовательных подчёркиваний одним при
    # формировании хештега.
    assert make_hashtag("A__B") == "#a_b"


def test_make_hashtag_preserves_existing_underscore():
    # Проверяет сохранение одиночного подчёркивания при приведении хештега к
    # нижнему регистру.
    assert make_hashtag("Web_Design") == "#web_design"
