import pytest

from fakes.factories import category, customer, project
from fakes.session import RecordingSession

from lansly.projects.gateways import (
    SACustomerGateway,
    SAProjectCategoryGateway,
    SAProjectGateway,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def session():
    return RecordingSession()


async def test_category_upsert_source_key(session):
    # Проверяет, что upsert категории разрешает конфликт по паре external_id и
    # source, обновляя название и родителя.
    await SAProjectCategoryGateway(session).upsert([category()])
    assert (
        "ON CONFLICT (external_id, source) DO UPDATE SET "
        "title = excluded.title, parent_id = excluded.parent_id" in session.sql
    )


async def test_category_lookup_source(session):
    # Проверяет наличие фильтров по внешним ID и площадке в запросе категорий.
    await SAProjectCategoryGateway(session).get_categories_by_external_ids(
        ["design"],
        "fl",
    )
    assert "project_categories.source =" in session.sql
    assert ["design"] in session.compiled.params.values()
    assert "fl" in session.compiled.params.values()


async def test_category_roots_source(session):
    # Проверяет, что запрос корневых категорий фильтрует площадку и отсутствие
    # родителя, а также сортирует по названию.
    await SAProjectCategoryGateway(session).get_root_categories("fl")
    assert "parent_id IS NULL" in session.sql
    assert "source =" in session.sql
    assert "ORDER BY project_categories.title" in session.sql


async def test_category_roots_all_sources(session):
    # Проверяет отсутствие фильтра по площадке при запросе всех корневых
    # категорий.
    await SAProjectCategoryGateway(session).get_root_categories()
    assert "source =" not in session.sql


@pytest.mark.parametrize("exact", [True, False])
async def test_project_insert_fields(session, exact):
    # Проверяет передачу площадки, признака точного бюджета и пустых связей с
    # категорией и заказчиком в INSERT проекта.
    await SAProjectGateway(session).bulk_insert(
        [project(category=None, has_exact_budget=exact)],
    )
    params = session.compiled.params
    assert params["has_exact_budget_m0"] is exact
    assert params["category_id_m0"] is None
    assert params["customer_id_m0"] is None
    assert params["source_m0"] == "fl"


async def test_project_insert_conflict_key(session):
    # Проверяет, что INSERT проекта игнорирует конфликт по external_id и source
    # и возвращает ID вставленных записей.
    p = project()
    session.rows = [p.id]
    assert await SAProjectGateway(session).bulk_insert([p]) == [p.id]
    assert (
        "ON CONFLICT (external_id, source) DO NOTHING RETURNING projects.id"
        in session.sql
    )


async def test_project_insert_empty(session):
    # Проверяет, что вставка пустого списка проектов возвращает пустой список
    # без SQL-запросов.
    assert await SAProjectGateway(session).bulk_insert([]) == []
    assert session.statements == []


async def test_project_missing_ids_source(session):
    # Проверяет вычисление отсутствующих внешних ID проектов и наличие фильтра
    # по площадке в SQL.
    session.rows = ["1"]
    assert await SAProjectGateway(session).get_missing_external_ids(
        ["1", "2"],
        "fl",
    ) == {"2"}
    assert "projects.source =" in session.sql
    assert "fl" in session.compiled.params.values()


async def test_customer_upsert_fields(session):
    # Проверяет передачу полей заказчика в upsert и возврат результата
    # сохранения.
    c = customer()
    session.rows = [c]
    assert await SACustomerGateway(session).bulk_upsert([c]) == [c]
    for key in [
        "username",
        "user_projects_count",
        "user_hired_percent",
        "source",
        "profile_picture",
    ]:
        assert session.compiled.params[key + "_m0"] == getattr(c, key)


async def test_customer_upsert_source_key(session):
    # Проверяет, что upsert заказчика разрешает конфликт по external_id и
    # source, обновляя данные без перезаписи ID.
    await SACustomerGateway(session).bulk_upsert([customer()])
    assert "ON CONFLICT (external_id, source) DO UPDATE SET" in session.sql
    update = session.sql.split("DO UPDATE SET")[1].split("RETURNING")[0]
    assert "id =" not in update
    assert "username = excluded.username" in update
