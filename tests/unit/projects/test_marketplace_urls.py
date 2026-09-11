import pytest

from fakes.factories import customer, project

from lansly.infra.fl.urls import FLUrlStrategy
from lansly.infra.kwork.urls import KworkUrlStrategy
from lansly.projects.urls import MarketplaceUrlBuilder


@pytest.mark.parametrize(("ref", "suffix"), [(None, ""), (123, "?ref=123")])
def test_kwork_project_url(ref, suffix):
    # Проверяет формирование ссылки на проект Kwork с реферальным параметром и
    # без него.
    assert (
        KworkUrlStrategy(ref).build_project_url(project())
        == "https://kwork.ru/projects/42" + suffix
    )


@pytest.mark.parametrize(("ref", "suffix"), [(None, ""), (123, "?ref=123")])
def test_kwork_customer_url(ref, suffix):
    # Проверяет формирование ссылки на профиль заказчика Kwork с реферальным
    # параметром и без него.
    assert (
        KworkUrlStrategy(ref).build_customer_url(customer())
        == "https://kwork.ru/user/alice" + suffix
    )


@pytest.mark.parametrize(("ref", "suffix"), [(None, ""), (123, "?ref=123")])
def test_fl_project_url(ref, suffix):
    # Проверяет формирование ссылки на проект FL.ru с реферальным параметром и
    # без него.
    assert (
        FLUrlStrategy(ref).build_project_url(project())
        == "https://fl.ru/projects/42/" + suffix
    )


def test_fl_customer_url():
    # Проверяет, что стратегия FL.ru не формирует ссылку на профиль заказчика.
    assert FLUrlStrategy().build_customer_url(customer()) is None


@pytest.mark.parametrize("strategy", [FLUrlStrategy, KworkUrlStrategy])
def test_zero_referral_id(strategy):
    # Проверяет, что нулевой реферальный ID включается в ссылку как ref=0 для
    # обеих площадок.
    assert strategy(0).build_project_url(project()).endswith("?ref=0")


@pytest.mark.parametrize(
    ("source", "url"),
    [
        ("fl", "https://fl.ru/projects/42/"),
        ("kwork", "https://kwork.ru/projects/42"),
    ],
)
def test_builder_source_selection(source, url):
    # Проверяет выбор стратегии по площадке и формирование соответствующих
    # ссылок на проект и заказчика.
    links = MarketplaceUrlBuilder(
        [FLUrlStrategy(), KworkUrlStrategy()],
    ).build_links(project(source=source, customer=customer()))
    assert links.project_url == url
    assert links.customer_url == (
        "https://kwork.ru/user/alice" if source == "kwork" else None
    )


def test_builder_without_customer():
    # Проверяет отсутствие ссылки на заказчика, если он не задан у проекта.
    links = MarketplaceUrlBuilder([KworkUrlStrategy()]).build_links(
        project(source="kwork"),
    )
    assert links.customer_url is None


def test_builder_unknown_source():
    # Проверяет, что запрос ссылок для неизвестной площадки вызывает
    # ValueError.
    with pytest.raises(ValueError, match="not configured"):
        MarketplaceUrlBuilder([FLUrlStrategy()]).build_links(
            project(source="unknown"),
        )


def test_builder_missing_strategy():
    # Проверяет, что построение ссылок без зарегистрированной стратегии
    # вызывает ValueError.
    with pytest.raises(ValueError, match="not configured"):
        MarketplaceUrlBuilder([]).build_links(project())


def test_builder_duplicate_strategy():
    # Проверяет, что регистрация двух стратегий для одной площадки вызывает
    # ValueError.
    with pytest.raises(ValueError, match="Duplicate"):
        MarketplaceUrlBuilder([FLUrlStrategy(), FLUrlStrategy()])
