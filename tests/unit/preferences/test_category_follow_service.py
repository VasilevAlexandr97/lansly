# ruff: noqa: PLR2004
from types import SimpleNamespace
from uuid import uuid7

import pytest

from fakes.factories import category
from fakes.follows import FollowGateway, Identity, Subscription
from fakes.infra import FakeTransactionManager

from lansly.preferences.consts import MAX_FREE_CATEGORIES, MAX_PRO_CATEGORIES
from lansly.preferences.exceptions import (
    UserCategoryFollowAlreadyExistsError,
    UserCategoryFollowLimitExceededError,
)
from lansly.preferences.services import UserCategoryFollowService
from lansly.projects.consts import Marketplace
from lansly.projects.exceptions import ProjectCategoryNotFoundError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx():
    root = category()
    child = category(parent_id=root.id, external_id="logo", title="Лого")
    gateway, identity, subscription, txn = (
        FollowGateway([root, child]),
        Identity(),
        Subscription(),
        FakeTransactionManager(),
    )
    return SimpleNamespace(
        root=root,
        child=child,
        gateway=gateway,
        identity=identity,
        subscription=subscription,
        txn=txn,
        service=UserCategoryFollowService(
            gateway,
            subscription,
            identity,
            txn,
        ),
    )


async def test_follow_new_category(ctx):
    # Проверяет создание активной подписки текущего пользователя, возврат
    # данных категории и фиксацию транзакции.
    result = await ctx.service.follow_category(ctx.child.id)
    (row,) = ctx.gateway.added
    assert (row.user_id, row.category_id, row.is_active) == (
        ctx.identity.user_id,
        ctx.child.id,
        True,
    )
    assert (result.category_id, result.title, ctx.txn.commits) == (
        ctx.child.id,
        "Лого",
        1,
    )


async def test_follow_active_category(ctx):
    # Проверяет, что повторная подписка на уже активную категорию возвращает её
    # без добавления записи и фиксации транзакции.
    row = ctx.gateway.seed(ctx.identity.user_id, ctx.child.id)
    result = await ctx.service.follow_category(ctx.child.id)
    assert result.category_id == row.category_id
    assert ctx.gateway.added == []
    assert ctx.txn.commits == 0


async def test_follow_active_at_limit(ctx):
    # Проверяет, что уже активную подписку можно повторно запросить даже при
    # достигнутом лимите категорий.
    ctx.gateway.seed(ctx.identity.user_id, ctx.child.id)
    ctx.gateway.count_override = MAX_PRO_CATEGORIES
    assert (await ctx.service.follow_category(ctx.child.id)).title == "Лого"
    assert ctx.txn.commits == 0


async def test_follow_inactive_category(ctx):
    # Проверяет восстановление неактивной подписки с обновлением времени и без
    # создания новой записи.
    row = ctx.gateway.seed(ctx.identity.user_id, ctx.child.id, active=False)
    old = row.updated_at
    await ctx.service.follow_category(ctx.child.id)
    assert row.is_active
    assert row.updated_at > old
    assert not ctx.gateway.added
    assert ctx.txn.commits == 1


@pytest.mark.parametrize(
    ("count", "allowed"),
    [(MAX_FREE_CATEGORIES - 1, True), (MAX_FREE_CATEGORIES, False)],
)
async def test_follow_free_limit(ctx, count, allowed):
    # Проверяет, что тариф FREE разрешает подписку до лимита и отклоняет её при
    # достижении лимита.
    ctx.gateway.count_override = count
    if allowed:
        await ctx.service.follow_category(ctx.child.id)
        assert ctx.txn.commits == 1
    else:
        with pytest.raises(UserCategoryFollowLimitExceededError) as exc:
            await ctx.service.follow_category(ctx.child.id)
        assert exc.value.limit == MAX_FREE_CATEGORIES
        assert ctx.txn.commits == 0


@pytest.mark.parametrize(
    ("count", "allowed"),
    [(MAX_PRO_CATEGORIES - 1, True), (MAX_PRO_CATEGORIES, False)],
)
async def test_follow_pro_limit(ctx, count, allowed):
    # Проверяет, что тариф PRO разрешает подписку до лимита и сообщает его
    # значение при отказе.
    ctx.subscription.pro = True
    ctx.gateway.count_override = count
    if allowed:
        await ctx.service.follow_category(ctx.child.id)
        assert ctx.txn.commits == 1
    else:
        with pytest.raises(UserCategoryFollowLimitExceededError) as exc:
            await ctx.service.follow_category(ctx.child.id)
        assert exc.value.limit == MAX_PRO_CATEGORIES


async def test_follow_shared_limit(ctx):
    # Проверяет, что подписка на Kwork учитывается в общем лимите при
    # добавлении категории FL.ru.
    other = category(source=Marketplace.KWORK, parent_id=uuid7())
    ctx.gateway.categories[other.id] = other
    ctx.gateway.seed(ctx.identity.user_id, other.id)
    with pytest.raises(UserCategoryFollowLimitExceededError):
        await ctx.service.follow_category(ctx.child.id)
    assert ctx.gateway.added == []


async def test_follow_reactivation_limit(ctx):
    # Проверяет, что достигнутый лимит не позволяет восстановить неактивную
    # подписку.
    row = ctx.gateway.seed(ctx.identity.user_id, ctx.child.id, active=False)
    ctx.gateway.count_override = MAX_FREE_CATEGORIES
    with pytest.raises(UserCategoryFollowLimitExceededError):
        await ctx.service.follow_category(ctx.child.id)
    assert not row.is_active
    assert ctx.txn.commits == 0


@pytest.mark.parametrize("root", [True, False])
async def test_follow_invalid_category(ctx, root):
    # Проверяет отказ в подписке на корневую или несуществующую категорию без
    # сохранения изменений.
    with pytest.raises(ProjectCategoryNotFoundError):
        await ctx.service.follow_category(ctx.root.id if root else uuid7())
    assert ctx.txn.commits == 0
    assert not ctx.gateway.added


async def test_follow_write_error(ctx):
    # Проверяет передачу ошибки записи подписки вызывающему коду без фиксации
    # транзакции.
    ctx.gateway.error = RuntimeError("write")
    with pytest.raises(RuntimeError, match="write"):
        await ctx.service.follow_category(ctx.child.id)
    assert ctx.txn.commits == 0


async def test_toggle_new_category(ctx):
    # Проверяет, что переключение категории без подписки включает её и
    # возвращает активный статус с лимитом FREE.
    result = await ctx.service.toggle_category_follow(ctx.child.id)
    assert result.categories[0].is_followed
    assert result.limit == MAX_FREE_CATEGORIES
    assert ctx.txn.commits == 1


async def test_toggle_active_category(ctx):
    # Проверяет, что переключение активной подписки отключает её даже при
    # достигнутом лимите категорий.
    row = ctx.gateway.seed(ctx.identity.user_id, ctx.child.id)
    ctx.gateway.count_override = MAX_PRO_CATEGORIES
    result = await ctx.service.toggle_category_follow(ctx.child.id)
    assert not row.is_active
    assert not result.categories[0].is_followed
    assert ctx.txn.commits == 1


async def test_toggle_inactive_category(ctx):
    # Проверяет, что переключение неактивной подписки включает её и обновляет
    # время изменения.
    row = ctx.gateway.seed(ctx.identity.user_id, ctx.child.id, active=False)
    old = row.updated_at
    await ctx.service.toggle_category_follow(ctx.child.id)
    assert row.is_active
    assert row.updated_at > old
    assert ctx.txn.commits == 1


@pytest.mark.parametrize(
    ("pro", "reactivate"),
    [(False, False), (False, True), (True, False), (True, True)],
)
async def test_toggle_limit_exceeded(ctx, pro, reactivate):
    # Проверяет отказ при добавлении или восстановлении подписки сверх лимита
    # FREE либо PRO.
    ctx.subscription.pro = pro
    ctx.gateway.count_override = (
        MAX_PRO_CATEGORIES if pro else MAX_FREE_CATEGORIES
    )
    if reactivate:
        ctx.gateway.seed(ctx.identity.user_id, ctx.child.id, active=False)
    with pytest.raises(UserCategoryFollowLimitExceededError):
        await ctx.service.toggle_category_follow(ctx.child.id)
    assert ctx.txn.commits == 0
    assert not ctx.gateway.added


@pytest.mark.parametrize("root", [True, False])
async def test_toggle_invalid_category(ctx, root):
    # Проверяет, что переключение корневой или несуществующей категории
    # вызывает ошибку отсутствия категории.
    with pytest.raises(ProjectCategoryNotFoundError):
        await ctx.service.toggle_category_follow(
            ctx.root.id if root else uuid7(),
        )


async def test_toggle_duplicate_add(ctx):
    # Проверяет, что ошибка дублирования подписки при переключении
    # обрабатывается возвратом категории без фиксации транзакции.
    ctx.gateway.error = UserCategoryFollowAlreadyExistsError()
    result = await ctx.service.toggle_category_follow(ctx.child.id)
    assert result.categories[0].category.id == ctx.child.id
    assert ctx.txn.commits == 0


async def test_follow_status_mapping(ctx):
    # Проверяет получение статуса подкатегории для текущего пользователя без
    # учёта чужой подписки.
    ctx.gateway.seed(uuid7(), ctx.child.id)
    result = await ctx.service.get_subcategories_with_follow_status(
        ctx.root.id,
    )
    assert result[0].category is ctx.child
    assert not result[0].is_followed
    assert ctx.gateway.calls == [
        ("subcategories", ctx.identity.user_id, ctx.root.id),
    ]


async def test_source_counts_mapping(ctx):
    # Проверяет преобразование счётчиков площадок в DTO и передачу ID текущего
    # пользователя шлюзу.
    ctx.gateway.source_counts = {Marketplace.KWORK: 2, Marketplace.FL: 3}
    result = await ctx.service.get_followed_category_counts_by_source()
    assert [(x.source, x.followed_count) for x in result] == [
        (Marketplace.KWORK, 2),
        (Marketplace.FL, 3),
    ]
    assert ctx.gateway.calls == [("sources", ctx.identity.user_id)]


@pytest.mark.parametrize("counts", [{}, {Marketplace.FL: 1}])
async def test_source_counts_default_zero(ctx, counts):
    # Проверяет, что площадки, отсутствующие в ответе шлюза, получают нулевой
    # счётчик подписок.
    ctx.gateway.source_counts = counts
    result = await ctx.service.get_followed_category_counts_by_source()
    assert {x.source: x.followed_count for x in result} == {
        Marketplace.KWORK: 0,
        Marketplace.FL: counts.get(Marketplace.FL, 0),
    }


async def test_direction_counts_mapping(ctx):
    # Проверяет преобразование данных направления и обоих счётчиков в DTO с
    # запросом для текущего пользователя и площадки.
    ctx.gateway.direction_counts = [(ctx.root.id, "Дизайн", 1, 4)]
    (row,) = await ctx.service.get_directions_with_follow_counts(
        Marketplace.FL,
    )
    assert (row.id, row.title, row.followed_count, row.total_count) == (
        ctx.root.id,
        "Дизайн",
        1,
        4,
    )
    assert ctx.gateway.calls == [
        ("directions", ctx.identity.user_id, Marketplace.FL),
    ]


async def test_direction_counts_empty(ctx):
    # Проверяет, что сервис возвращает пустой список, если шлюз не вернул
    # направления со счётчиками подписок.
    assert (
        await ctx.service.get_directions_with_follow_counts(Marketplace.FL)
        == []
    )


async def test_unfollow_all(ctx):
    # Проверяет отключение всех подписок текущего пользователя с сохранением
    # чужих подписок и фиксацией транзакции.
    mine = ctx.gateway.seed(ctx.identity.user_id, ctx.child.id)
    other = ctx.gateway.seed(uuid7(), ctx.child.id)
    await ctx.service.unfollow_all_categories()
    assert not mine.is_active
    assert other.is_active
    assert ctx.txn.commits == 1


async def test_unfollow_all_empty(ctx):
    # Проверяет, что повторное отключение подписок при их отсутствии не создаёт
    # записей и каждый раз фиксирует транзакцию.
    await ctx.service.unfollow_all_categories()
    await ctx.service.unfollow_all_categories()
    assert ctx.txn.commits == 2
    assert not ctx.gateway.follows
