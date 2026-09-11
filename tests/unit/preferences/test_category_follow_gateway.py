# ruff: noqa: PLR2004
from uuid import uuid7

import pytest

from fakes.session import RecordingSession

from lansly.preferences.gateways import UserCategoryFollowGateway

pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx():
    session = RecordingSession()
    return UserCategoryFollowGateway(session), session, uuid7()


async def test_source_counts_query(ctx):
    # Проверяет, что SQL подсчёта подписок группирует категории по площадке и
    # учитывает активные подписки заданного пользователя.
    gateway, session, uid = ctx
    await gateway.get_followed_category_counts_by_source(uid)
    assert "GROUP BY project_categories.source" in session.sql
    assert "user_category_follows.user_id =" in session.sql
    assert "user_category_follows.is_active IS true" in session.sql
    assert uid in session.compiled.params.values()


async def test_source_counts_zero_preserved(ctx):
    # Проверяет использование LEFT JOIN и подсчёта связанных подписок в запросе
    # счётчиков по площадкам.
    await ctx[0].get_followed_category_counts_by_source(ctx[2])
    assert "LEFT OUTER JOIN user_category_follows ON" in ctx[1].sql
    assert "count(user_category_follows.category_id)" in ctx[1].sql


@pytest.mark.parametrize("rows", [[], [("fl", 2), ("kwork", 0)]])
async def test_source_counts_result(ctx, rows):
    # Проверяет преобразование строк со счётчиками по площадкам в словарь,
    # включая пустой результат.
    ctx[1].rows = rows
    assert await ctx[0].get_followed_category_counts_by_source(ctx[2]) == dict(
        rows,
    )


async def test_direction_counts_query(ctx):
    # Проверяет, что SQL счётчиков направлений фильтрует корневые и дочерние
    # категории по площадке и группирует подкатегории по родителю.
    await ctx[0].get_directions_with_follow_counts(ctx[2], "fl")
    sql = ctx[1].sql
    assert sql.count("project_categories.source =") == 2
    assert "parent_id IS NOT NULL" in sql
    assert "parent_id IS NULL" in sql
    assert "GROUP BY project_categories.parent_id" in sql
    assert "fl" in ctx[1].compiled.params.values()


async def test_direction_counts_user_filter(ctx):
    # Проверяет, что запрос счётчиков направлений учитывает только активные
    # подписки заданного пользователя.
    await ctx[0].get_directions_with_follow_counts(ctx[2], "fl")
    assert "user_category_follows.user_id =" in ctx[1].sql
    assert "is_active IS true" in ctx[1].sql
    assert ctx[2] in ctx[1].compiled.params.values()


async def test_direction_counts_zero_preserved(ctx):
    # Проверяет использование LEFT JOIN и coalesce для счётчиков направлений, а
    # также подсчёт категорий в SQL.
    await ctx[0].get_directions_with_follow_counts(ctx[2], "fl")
    assert ctx[1].sql.count("LEFT OUTER JOIN") == 2
    assert ctx[1].sql.count("coalesce(") == 2
    assert "count(project_categories.id)" in ctx[1].sql


async def test_direction_counts_order(ctx):
    # Проверяет возврат строк со счётчиками направлений и наличие сортировки по
    # названию в SQL.
    ctx[1].rows = [(uuid7(), "Дизайн", 0, 2)]
    assert (
        await ctx[0].get_directions_with_follow_counts(ctx[2], "fl")
        == ctx[1].rows
    )
    assert "ORDER BY project_categories.title" in ctx[1].sql


async def test_subcategory_status_query(ctx):
    # Проверяет, что запрос статусов подкатегорий учитывает родителя,
    # пользователя и активность подписки через LEFT JOIN.
    parent = uuid7()
    await ctx[0].get_subcategories_with_follow_status(ctx[2], parent)
    assert "LEFT OUTER JOIN" in ctx[1].sql
    assert "is_active IS true" in ctx[1].sql
    assert parent in ctx[1].compiled.params.values()
    assert ctx[2] in ctx[1].compiled.params.values()
    assert "user_category_follows.user_id IS NOT NULL" in ctx[1].sql


async def test_deactivate_all_query(ctx):
    # Проверяет, что массовая отписка формирует UPDATE с is_active=False только
    # для заданного пользователя.
    # Массовая деактивация текущей реализации меняет только is_active.
    await ctx[0].deactivate_all(ctx[2])
    assert "UPDATE user_category_follows SET is_active=" in ctx[1].sql
    assert ctx[2] in ctx[1].compiled.params.values()
    assert False in ctx[1].compiled.params.values()
    assert "WHERE user_category_follows.user_id =" in ctx[1].sql
