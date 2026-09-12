# ruff: noqa: PLR2004
from types import SimpleNamespace

import pytest

from fakes.factories import category, marketplace_project
from fakes.infra import FakeDistributedLockManager, FakeTransactionManager
from fakes.projects import (
    FakeCustomerGateway,
    FakeProjectCategoryGateway,
    FakeProjectCollector,
    FakeProjectGateway,
)

from lansly.projects.dto import MarketplaceCustomer
from lansly.projects.integrations import LockOptions, MarketplaceIntegration
from lansly.projects.services import ProjectSyncService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx():
    collector = FakeProjectCollector(
        source="fl",
        projects=[marketplace_project()],
    )
    gateway, customers, categories, txn, lock = (
        FakeProjectGateway(),
        FakeCustomerGateway(),
        FakeProjectCategoryGateway([category()]),
        FakeTransactionManager(),
        FakeDistributedLockManager(),
    )
    service = ProjectSyncService(
        [MarketplaceIntegration(collector)],
        categories,
        gateway,
        customers,
        txn,
        lock,
    )
    return SimpleNamespace(
        collector=collector,
        gateway=gateway,
        customers=customers,
        categories=categories,
        txn=txn,
        lock=lock,
        service=service,
    )


async def test_sync_source_selection(ctx):
    # Проверяет, что синхронизация запускает сборщик только выбранной площадки.
    other = FakeProjectCollector(source="kwork")
    ctx.service.integrations["kwork"] = MarketplaceIntegration(other)
    await ctx.service.sync("fl")
    assert ctx.collector.collect_calls == 1
    assert other.collect_calls == 0


async def test_sync_cross_source_ids(ctx):
    # Проверяет раздельное сохранение проектов и заказчиков разных площадок с
    # совпадающими внешними ID.
    ctx.collector.projects[0].customer = MarketplaceCustomer("7", "fl-user")
    other = FakeProjectCollector(
        source="kwork",
        projects=[
            marketplace_project(
                source="kwork",
                customer=MarketplaceCustomer("7", "kwork-user"),
            ),
        ],
    )
    ctx.service.integrations["kwork"] = MarketplaceIntegration(other)
    await ctx.service.sync("fl")
    await ctx.service.sync("kwork")
    assert len(ctx.gateway.bulk_inserted) == 2
    assert {c.source for c in ctx.customers.upserted} == {"fl", "kwork"}
    assert len({p.id for p in ctx.gateway.bulk_inserted}) == 2


@pytest.mark.parametrize(("exact", "price"), [(True, 30000), (False, 0)])
async def test_sync_fl_budget(ctx, exact, price):
    # Проверяет сохранение цены, верхней границы бюджета и признака точного
    # бюджета проекта FL.ru.
    ctx.collector.projects = [
        marketplace_project(
            has_exact_budget=exact,
            price=price,
            possible_price_limit=price,
        ),
    ]
    await ctx.service.sync("fl")
    (p,) = ctx.gateway.bulk_inserted
    assert (p.price, p.possible_price_limit, p.has_exact_budget) == (
        price,
        price,
        exact,
    )


async def test_sync_fl_without_customer(ctx):
    # Проверяет, что проект FL.ru без заказчика сохраняется с customer_id=None
    # без обращения к сохранению заказчиков.
    await ctx.service.sync("fl")
    assert ctx.gateway.bulk_inserted[0].customer_id is None
    assert ctx.customers.upsert_calls == 0


async def test_sync_no_category(ctx):
    # Проверяет сохранение проекта без категории с category_id=None.
    ctx.collector.projects[0].category_id = None
    await ctx.service.sync("fl")
    assert ctx.gateway.bulk_inserted[0].category_id is None


async def test_sync_unknown_category(ctx, caplog):
    # Проверяет сохранение проекта без связи с неизвестной категорией и
    # упоминание её ID в журнале.
    ctx.collector.projects[0].category_id = "unknown"
    await ctx.service.sync("fl")
    assert ctx.gateway.bulk_inserted[0].category_id is None
    assert "unknown" in caplog.text


async def test_sync_repeat(ctx):
    # Проверяет, что повторная синхронизация не вставляет уже сохранённые
    # проекты и возвращает пустой список.
    await ctx.service.sync("fl")
    assert await ctx.service.sync("fl") == []
    assert ctx.gateway.bulk_insert_calls == 1
    assert ctx.txn.commits == 1


async def test_sync_duplicate_first_wins(ctx):
    # Проверяет, что при дублировании проектов и заказчиков сохраняются данные
    # первого вхождения.
    ctx.collector.projects = [
        marketplace_project(
            title="First",
            customer=MarketplaceCustomer("7", "first"),
        ),
        marketplace_project(title="Last"),
        marketplace_project(
            id="43",
            customer=MarketplaceCustomer("7", "last"),
        ),
    ]
    await ctx.service.sync("fl")
    assert [p.title for p in ctx.gateway.bulk_inserted] == ["First", "Проект"]
    assert len(ctx.customers.upserted) == 1
    assert ctx.customers.upserted[0].username == "first"


async def test_sync_empty_insert_result(ctx):
    # Проверяет, что пустой результат вставки проектов возвращается без
    # фиксации транзакции.
    class ConflictingGateway(FakeProjectGateway):
        async def bulk_insert(self, projects):
            del projects
            return []

    ctx.service.project_gateway = ConflictingGateway()
    assert await ctx.service.sync("fl") == []
    assert ctx.txn.commits == 0


async def test_sync_source_mismatch_no_writes(ctx):
    # Проверяет, что проект другой площадки вызывает ошибку до сохранения
    # проектов и заказчиков.
    ctx.collector.projects.append(marketplace_project(source="kwork"))
    with pytest.raises(ValueError, match="source mismatch"):
        await ctx.service.sync("fl")
    assert not ctx.gateway.bulk_inserted
    assert not ctx.customers.upserted


async def test_sync_customer_fields(ctx):
    # Проверяет сохранение полей заказчика и привязку проекта к его внутреннему
    # ID.
    ctx.collector.projects[0].customer = MarketplaceCustomer(
        "7",
        "alice",
        "avatar",
        12,
        75,
    )
    await ctx.service.sync("fl")
    (c,) = ctx.customers.upserted
    assert (
        c.username,
        c.profile_picture,
        c.user_projects_count,
        c.user_hired_percent,
    ) == ("alice", "avatar", 12, 75)
    assert ctx.gateway.bulk_inserted[0].customer_id == c.id


async def test_sync_gateway_error(ctx):
    # Проверяет передачу ошибки сохранения проектов вызывающему коду без
    # фиксации транзакции.
    class FailingGateway(FakeProjectGateway):
        async def bulk_insert(self, projects):
            del projects
            raise RuntimeError("save")

    ctx.service.project_gateway = FailingGateway()
    with pytest.raises(RuntimeError, match="save"):
        await ctx.service.sync("fl")
    assert ctx.txn.commits == 0


async def test_sync_lock_options(ctx):
    # Проверяет передачу ключа, времени ожидания и режима блокировки из
    # настроек интеграции менеджеру блокировок.
    ctx.service.integrations["fl"] = MarketplaceIntegration(
        ctx.collector,
        LockOptions("fl-key", 20, blocking=True, blocking_timeout=3),
    )
    await ctx.service.sync("fl")
    (call,) = ctx.lock.calls
    assert (call.key, call.timeout, call.blocking, call.blocking_timeout) == (
        "fl-key",
        20,
        True,
        3,
    )


async def test_sync_lock_release_after_failure(ctx):
    # Проверяет выход из контекста блокировки при ошибке сборщика с передачей
    # исключения вызывающему коду.
    class FailingCollector:
        source = "fl"

        async def collect(self):
            raise RuntimeError("collect")

    ctx.service.integrations["fl"] = MarketplaceIntegration(
        FailingCollector(),
        LockOptions("fl-key", 20),
    )
    with pytest.raises(RuntimeError, match="collect"):
        await ctx.service.sync("fl")
    assert ctx.lock.enter_count == ctx.lock.exit_count == 1


async def test_sync_description_spacing(ctx):
    # Проверяет очистку описания от HTML и краевых пробелов с декодированием
    # сущностей и сохранением абзацев.
    ctx.collector.projects[
        0
    ].description = "  Первый <b>важный</b> абзац<br><br>Второй &amp; третий  "
    await ctx.service.sync("fl")
    assert (
        ctx.gateway.bulk_inserted[0].description
        == "Первый важный абзац\n\nВторой & третий"
    )
