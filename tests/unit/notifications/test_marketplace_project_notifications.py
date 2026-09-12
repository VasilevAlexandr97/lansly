# ruff: noqa: PLR2004, SLF001
from types import SimpleNamespace
from uuid import uuid7

import pytest

from fakes.factories import project
from fakes.infra import FakeTransactionManager
from fakes.notifications import (
    Filters,
    MemoryRedis,
    NotificationProjects,
    NotificationStore,
    Notifier,
    Recipients,
)

from lansly.infra.fl.urls import FLUrlStrategy
from lansly.infra.kwork.urls import KworkUrlStrategy
from lansly.notifications.services import ProjectNotificationService
from lansly.projects.urls import MarketplaceUrlBuilder

pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx():
    p = project()
    user = SimpleNamespace(id=uuid7(), telegram_id=123)
    (
        projects,
        recipients,
        filters,
        store,
        channel_store,
        notifier,
        txn,
        redis,
    ) = (
        NotificationProjects([p]),
        Recipients([user]),
        Filters(),
        NotificationStore(),
        NotificationStore(),
        Notifier(),
        FakeTransactionManager(),
        MemoryRedis(),
    )
    service = ProjectNotificationService(
        projects,
        recipients,
        filters,
        filters,
        store,
        channel_store,
        notifier,
        txn,
        MarketplaceUrlBuilder([FLUrlStrategy(7), KworkUrlStrategy(8)]),
        redis,
        channel_id=-100,
    )
    return SimpleNamespace(
        p=p,
        user=user,
        projects=projects,
        recipients=recipients,
        filters=filters,
        store=store,
        channel_store=channel_store,
        notifier=notifier,
        txn=txn,
        redis=redis,
        service=service,
    )


@pytest.mark.parametrize(
    ("source", "label", "url"),
    [
        ("fl", "FL", "https://fl.ru/projects/42/?ref=7"),
        ("kwork", "KWORK", "https://kwork.ru/projects/42?ref=8"),
    ],
)
async def test_user_marketplace_template(ctx, source, label, url):
    # Проверяет, что уведомление пользователю содержит название площадки и
    # реферальную ссылку на проект.
    ctx.p.source = source
    await ctx.service.notify_new_projects([ctx.p.id])
    (sent,) = ctx.notifier.sent
    assert label in sent["text"]
    assert url in sent["text"]
    assert sent["chat_id"] == 123


async def test_user_project_keyboard(ctx):
    # Проверяет, что кнопка проекта и текст уведомления содержат одну и ту же
    # реферальную ссылку.
    await ctx.service.notify_new_projects([ctx.p.id])
    (sent,) = ctx.notifier.sent
    links = [
        b.url for row in sent["keyboard"].inline_keyboard for b in row if b.url
    ]
    assert links == ["https://fl.ru/projects/42/?ref=7"]
    assert links[0] in sent["text"]


async def test_user_followed_category(ctx):
    # Проверяет поиск получателей по категории проекта и отправку уведомления
    # найденному пользователю.
    await ctx.service.notify_new_projects([ctx.p.id])
    assert ctx.recipients.categories == [ctx.p.category_id]
    assert [s["chat_id"] for s in ctx.notifier.sent] == [ctx.user.telegram_id]


async def test_user_without_telegram(ctx):
    # Проверяет, что пользователю без Telegram ID уведомление не отправляется и
    # запись об отправке не создаётся.
    ctx.user.telegram_id = None
    await ctx.service.notify_new_projects([ctx.p.id])
    assert not ctx.notifier.sent
    assert not ctx.store.rows


async def test_user_without_category(ctx):
    # Проверяет, что для проекта без категории получатели не запрашиваются и
    # уведомления не отправляются.
    ctx.p.category_id = None
    await ctx.service.notify_new_projects([ctx.p.id])
    assert not ctx.notifier.sent
    assert not ctx.recipients.categories


@pytest.mark.parametrize("source", ["fl", "kwork"])
@pytest.mark.parametrize("word", ["ЛОГОТИП", "ПРОБЕЛАМИ"])
async def test_user_stop_words(ctx, source, word):
    # Проверяет, что стоп-слова в верхнем регистре блокируют уведомления о
    # проектах обеих площадок.
    ctx.p.source = source
    ctx.filters.words[ctx.user.id] = [word]
    await ctx.service.notify_new_projects([ctx.p.id])
    assert not ctx.notifier.sent
    assert ctx.txn.commits == 0


@pytest.mark.parametrize("source", ["fl", "kwork"])
@pytest.mark.parametrize(
    ("price", "allowed"),
    [(99, False), (100, True), (200, True), (201, False)],
)
async def test_user_price_bounds(ctx, source, price, allowed):
    # Проверяет, что ценовой фильтр допускает обе границы диапазона и исключает
    # цены за его пределами.
    ctx.p.source, ctx.p.price = source, price
    ctx.filters.prices[ctx.user.id] = (100, 200)
    await ctx.service.notify_new_projects([ctx.p.id])
    assert bool(ctx.notifier.sent) is allowed


async def test_user_negotiable_price_filter(ctx):
    # Проверяет, что проект с договорным бюджетом и нулевой ценой не проходит
    # фильтр с положительной нижней границей.
    ctx.p.price, ctx.p.has_exact_budget = 0, False
    ctx.filters.prices[ctx.user.id] = (1, 100)
    await ctx.service.notify_new_projects([ctx.p.id])
    assert not ctx.notifier.sent


async def test_user_without_filters(ctx):
    # Проверяет отправку уведомления пользователю, у которого не заданы
    # фильтры.
    await ctx.service.notify_new_projects([ctx.p.id])
    assert len(ctx.notifier.sent) == 1


async def test_user_success_saved(ctx):
    # Проверяет сохранение ID проекта, ID получателя и времени успешной
    # отправки с фиксацией транзакции.
    await ctx.service.notify_new_projects([ctx.p.id])
    (row,) = ctx.store.rows
    assert (row.project_id, row.user_id) == (ctx.p.id, ctx.user.id)
    assert row.sent_at.tzinfo is not None
    assert ctx.txn.commits == 1


async def test_user_send_failure(ctx):
    # Проверяет, что сбой отправки одному пользователю не мешает уведомить
    # другого и сохранить его отправку.
    ctx.notifier.fail_chats.add(ctx.user.telegram_id)
    other = SimpleNamespace(id=uuid7(), telegram_id=456)
    ctx.recipients.users.append(other)
    await ctx.service.notify_new_projects([ctx.p.id])
    assert [s["chat_id"] for s in ctx.notifier.sent] == [456]
    assert [r.user_id for r in ctx.store.rows] == [other.id]


@pytest.mark.parametrize("empty_projects", [True, False])
async def test_user_no_deliveries(ctx, empty_projects):
    # Проверяет, что без проектов или получателей записи об отправке не
    # создаются и транзакция не фиксируется.
    ctx.recipients.users = []
    await ctx.service.notify_new_projects([] if empty_projects else [ctx.p.id])
    assert not ctx.store.rows
    assert ctx.txn.commits == 0


async def test_user_lock(ctx):
    # Проверяет получение и освобождение блокировки при отправке уведомлений
    # пользователям.
    await ctx.service.notify_new_projects([ctx.p.id])
    assert ctx.redis.acquires == ctx.redis.releases == 1
    assert not ctx.redis.values


@pytest.mark.parametrize(
    ("source", "label"),
    [("fl", "FL"), ("kwork", "KWORK")],
)
async def test_channel_marketplace_template(ctx, source, label):
    # Проверяет отправку в канал шаблона нужной площадки с согласованными
    # ссылками и сохранением результата.
    ctx.p.source = source
    await ctx.service.notify_new_projects_to_channel([ctx.p.id])
    (sent,) = ctx.notifier.sent
    assert sent["chat_id"] == -100
    assert label in sent["text"]
    assert sent["keyboard"].inline_keyboard[0][0].url in sent["text"]
    assert ctx.channel_store.rows[0].project_id == ctx.p.id
    assert ctx.txn.commits == 1


async def test_channel_disabled(ctx):
    # Проверяет, что при отключённом канале проекты не запрашиваются и
    # уведомления не отправляются.
    ctx.service.channel_id = None
    await ctx.service.notify_new_projects_to_channel([ctx.p.id])
    assert not ctx.projects.calls
    assert not ctx.notifier.sent


@pytest.mark.parametrize(
    ("price", "allowed"),
    [(29999, False), (30000, True), (30001, True)],
)
async def test_channel_price_threshold(ctx, price, allowed):
    # Проверяет, что в канал попадают проекты с ценой от 30 000 рублей
    # включительно.
    ctx.p.price = price
    await ctx.service.notify_new_projects_to_channel([ctx.p.id])
    assert bool(ctx.notifier.sent) is allowed


async def test_channel_without_category(ctx):
    # Проверяет, что проект без категории не отправляется в канал.
    ctx.p.category_id = None
    await ctx.service.notify_new_projects_to_channel([ctx.p.id])
    assert not ctx.notifier.sent


async def test_channel_send_failure(ctx):
    # Проверяет, что после ошибки отправки первого проекта в канал второй
    # отправляется и сохраняется.
    # Ошибка отправки первого проекта не мешает отправке второго.
    ctx.notifier.fail_next = 1
    other = project()
    ctx.projects.projects.append(other)
    await ctx.service.notify_new_projects_to_channel([ctx.p.id, other.id])
    assert len(ctx.notifier.sent) == 1
    assert [r.project_id for r in ctx.channel_store.rows] == [other.id]


async def test_channel_no_deliveries(ctx):
    # Проверяет, что при неудачной отправке в канал запись об уведомлении не
    # создаётся и транзакция не фиксируется.
    ctx.notifier.fail_chats.add(-100)
    await ctx.service.notify_new_projects_to_channel([ctx.p.id])
    assert not ctx.channel_store.rows
    assert ctx.txn.commits == 0


async def test_unsupported_source(ctx):
    # Проверяет, что построение сообщения для неподдерживаемой площадки
    # вызывает ValueError.
    ctx.p.source = "unknown"
    with pytest.raises(ValueError, match="not supported"):
        ctx.service._get_project_message(ctx.p, None)
