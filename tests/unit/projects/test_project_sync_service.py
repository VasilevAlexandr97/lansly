# ruff: noqa: PLR2004, SLF001
import logging

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import pytest

from fakes.factories import (
    category,
    marketplace_project,
    project as make_saved_project,
)
from fakes.infra import (
    FakeDistributedLockManager,
    FakeTransactionManager,
    LockCall,
)
from fakes.notifications import FakeProjectNotificationQueue
from fakes.projects import (
    FakeCustomerGateway,
    FakeProjectCategoryGateway,
    FakeProjectCollector,
    FakeProjectGateway,
)

from lansly.projects.consts import Marketplace
from lansly.projects.dto import MarketplaceCustomer, MarketplaceProject
from lansly.projects.exceptions import MarketplaceIntegrationNotFoundError
from lansly.projects.integrations import LockOptions, MarketplaceIntegration
from lansly.projects.models import ProjectCategory
from lansly.projects.services import ProjectSyncService


def make_customer(
    external_id: str,
    *,
    username: str = "testuser",
    user_projects_count: int = 10,
    user_hired_percent: int = 50,
) -> MarketplaceCustomer:
    return MarketplaceCustomer(
        id=external_id,
        username=username,
        user_projects_count=user_projects_count,
        user_hired_percent=user_hired_percent,
    )


def make_project(
    external_id: str,
    category_id: str | None,
    *,
    title: str = "Title",
    source: Marketplace = Marketplace.KWORK,
    description: str = "Description",
    price: int = 100,
    possible_price_limit: int = 200,
    has_exact_budget: bool = False,
    offers: int = 3,
    customer: MarketplaceCustomer | None = None,
) -> MarketplaceProject:
    return MarketplaceProject(
        id=external_id,
        category_id=category_id,
        source=source,
        price=price,
        possible_price_limit=possible_price_limit,
        has_exact_budget=has_exact_budget,
        title=title,
        description=description,
        offers=offers,
        customer=customer,
    )


def make_category(
    external_id: str,
    title: str,
) -> ProjectCategory:
    return ProjectCategory(
        id=uuid7(),
        external_id=external_id,
        source=Marketplace.KWORK,
        title=title,
        parent_id=None,
    )


# ---------------------------------------------------------------------------
# sync()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("previous_expiry", "offset", "expected_notification"),
    [
        (False, 0, True),
        (True, 0, False),
        (True, 120, False),
        (True, 300, False),
        (True, 301, True),
        (True, 86400, True),
        (True, -600, False),
        (True, None, False),
    ],
)
async def test_sync_expiry_change_enqueues_once(
    *,
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    notification_queue: FakeProjectNotificationQueue,
    previous_expiry: bool,
    offset: int | None,
    expected_notification: bool,
):
    deadline = datetime(2026, 10, 2, 18, 30, tzinfo=UTC)
    saved = make_saved_project(
        external_id="3246596",
        source=Marketplace.KWORK,
        title="Title",
        description="Description",
        price=100,
        created_at=deadline - timedelta(days=30),
        updated_at=deadline - timedelta(days=30),
        expires_at=deadline if previous_expiry else None,
    )
    project_gateway.existing = [saved]
    original_created_at, original_updated_at = (
        saved.created_at,
        saved.updated_at,
    )
    incoming = make_project("3246596", None)
    incoming.expires_at = (
        deadline + timedelta(seconds=offset) if offset is not None else None
    )
    project_collector.source = Marketplace.KWORK
    project_collector.projects = [incoming]
    sync_service.integrations = {
        Marketplace.KWORK: MarketplaceIntegration(project_collector),
    }

    result = await sync_service.sync(Marketplace.KWORK)
    assert result == ([saved.id] if expected_notification else [])
    assert notification_queue.enqueued == (
        [[saved.id]] if expected_notification else []
    )
    assert saved.created_at == original_created_at
    if expected_notification:
        assert saved.expires_at == incoming.expires_at
        assert saved.updated_at > original_updated_at
    else:
        assert saved.expires_at == deadline
        assert saved.updated_at == original_updated_at

    assert await sync_service.sync(Marketplace.KWORK) == []
    assert len(notification_queue.enqueued) == int(expected_notification)


@pytest.mark.asyncio
async def test_sync_without_lock_collects_and_saves_projects(
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
):
    # Проверяет сбор и сохранение проектов без обращения к блокировке с
    # возвратом ID и фиксацией транзакции.
    """Интеграция без lock собирает и сохраняет проекты напрямую."""
    project_collector.source = Marketplace.KWORK
    project_collector.projects = [make_project("p1", "1")]
    integration = MarketplaceIntegration(
        collector=project_collector,
        lock=None,
    )
    sync_service.integrations = {Marketplace.KWORK: integration}

    result = await sync_service.sync(Marketplace.KWORK)

    assert project_collector.collect_calls == 1
    assert lock_manager.calls == []
    assert project_gateway.bulk_upsert_calls == 1
    assert txn.commits == 1
    assert result == [project.id for project in project_gateway.bulk_inserted]


@pytest.mark.asyncio
async def test_sync_with_acquired_lock_collects_and_saves_projects(
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
):
    # Проверяет сбор и сохранение проектов при полученной блокировке, передачу
    # её настроек и выход из контекста.
    """При полученном lock синхронизация выполняется с его настройками."""
    project_collector.source = Marketplace.FL
    project_collector.projects = [
        make_project("p1", "1", source=Marketplace.FL),
    ]
    lock = LockOptions(
        key="projects:sync:fl",
        timeout=300,
        blocking=True,
        blocking_timeout=5,
    )
    integration = MarketplaceIntegration(
        collector=project_collector,
        lock=lock,
    )
    sync_service.integrations = {Marketplace.FL: integration}
    result = await sync_service.sync(Marketplace.FL)

    assert project_collector.collect_calls == 1
    assert project_gateway.bulk_upsert_calls == 1
    assert txn.commits == 1
    assert result == [project.id for project in project_gateway.bulk_inserted]

    assert lock_manager.calls == [
        LockCall(
            key="projects:sync:fl",
            timeout=300,
            blocking=True,
            blocking_timeout=5,
        ),
    ]
    assert lock_manager.enter_count == 1
    assert lock_manager.exit_count == 1


@pytest.mark.asyncio
async def test_sync_with_busy_lock_does_not_start_collector(
    *,
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
):
    # Проверяет, что занятая блокировка приводит к пустому результату без
    # запуска сборщика и сохранения данных.
    """При занятом lock синхронизация не запускает collector."""
    lock_manager.acquired = False
    project_collector.source = Marketplace.FL
    project_collector.projects = [
        make_project("p1", "1", source=Marketplace.FL),
    ]
    lock = LockOptions(
        key="projects:sync:fl",
        timeout=300,
        blocking=False,
    )
    integration = MarketplaceIntegration(
        collector=project_collector,
        lock=lock,
    )
    sync_service.integrations = {Marketplace.FL: integration}

    result = await sync_service.sync(Marketplace.FL)

    assert result == []
    assert project_collector.collect_calls == 0
    assert project_gateway.bulk_upsert_calls == 0
    assert customer_gateway.upsert_calls == 0
    assert txn.commits == 0

    assert lock_manager.enter_count == 1
    assert lock_manager.exit_count == 1


@pytest.mark.asyncio
async def test_sync_raises_when_integration_not_found(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
):
    # Проверяет, что отсутствующая интеграция вызывает ошибку до вставки
    # проектов.
    """Для незарегистрированного источника выбрасывается исключение."""
    with pytest.raises(MarketplaceIntegrationNotFoundError):
        await sync_service.sync(Marketplace.KWORK)

    assert project_gateway.bulk_upsert_calls == 0


@pytest.mark.asyncio
async def test_sync_source_selection(
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    category_gateway: FakeProjectCategoryGateway,
):
    # Проверяет, что синхронизация запускает сборщик только выбранной площадки.
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    other = FakeProjectCollector(source=Marketplace.KWORK)
    sync_service.integrations[Marketplace.KWORK] = MarketplaceIntegration(
        other,
    )
    await sync_service.sync(Marketplace.FL)
    assert project_collector.collect_calls == 1
    assert other.collect_calls == 0


@pytest.mark.asyncio
async def test_sync_cross_source_ids(
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    category_gateway: FakeProjectCategoryGateway,
):
    # Проверяет раздельное сохранение проектов и заказчиков разных площадок с
    # совпадающими внешними ID.
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    project_collector.projects[0].customer = MarketplaceCustomer(
        "7",
        "fl-user",
    )
    other = FakeProjectCollector(
        source=Marketplace.KWORK,
        projects=[
            marketplace_project(
                source=Marketplace.KWORK,
                customer=MarketplaceCustomer("7", "kwork-user"),
            ),
        ],
    )
    sync_service.integrations[Marketplace.KWORK] = MarketplaceIntegration(
        other,
    )
    await sync_service.sync(Marketplace.FL)
    await sync_service.sync(Marketplace.KWORK)
    assert len(project_gateway.bulk_inserted) == 2
    assert {c.source for c in customer_gateway.upserted} == {
        Marketplace.FL,
        Marketplace.KWORK,
    }
    assert len({p.id for p in project_gateway.bulk_inserted}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("exact", "price"), [(True, 30000), (False, 0)])
async def test_sync_fl_budget(
    *,
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    exact: bool,
    price: int,
    category_gateway: FakeProjectCategoryGateway,
):
    # Проверяет сохранение цены, верхней границы бюджета и признака точного
    # бюджета проекта FL.ru.
    project_collector.source = Marketplace.FL
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    project_collector.projects = [
        marketplace_project(
            has_exact_budget=exact,
            price=price,
            possible_price_limit=price,
        ),
    ]
    await sync_service.sync(Marketplace.FL)
    (p,) = project_gateway.bulk_inserted
    assert (p.price, p.possible_price_limit, p.has_exact_budget) == (
        price,
        price,
        exact,
    )


@pytest.mark.asyncio
async def test_sync_repeat(
    *,
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    notification_queue: FakeProjectNotificationQueue,
    project_collector: FakeProjectCollector,
    category_gateway: FakeProjectCategoryGateway,
):
    # Проверяет, что повторная синхронизация не вставляет уже сохранённые
    # проекты и возвращает пустой список.
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    await sync_service.sync(Marketplace.FL)
    assert await sync_service.sync(Marketplace.FL) == []
    assert project_gateway.bulk_upsert_calls == 1
    assert txn.commits == 1
    assert notification_queue.enqueued == [
        [project_gateway.bulk_inserted[0].id],
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("title", "Updated"), ("description", "Updated"), ("price", 500)],
)
async def test_sync_changed_project_enqueues_same_id(
    *,
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    project_gateway: FakeProjectGateway,
    notification_queue: FakeProjectNotificationQueue,
    field: str,
    value: str | int,
    category_gateway: FakeProjectCategoryGateway,
):
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    await sync_service.sync(Marketplace.FL)
    saved = project_gateway.bulk_inserted[0]
    original_id, original_updated_at = saved.id, saved.updated_at
    setattr(project_collector.projects[0], field, value)

    assert await sync_service.sync(Marketplace.FL) == [original_id]
    assert saved.updated_at > original_updated_at
    assert notification_queue.enqueued == [[original_id], [original_id]]
    assert await sync_service.sync(Marketplace.FL) == []
    assert len(notification_queue.enqueued) == 2


@pytest.mark.asyncio
async def test_sync_enqueues_after_commit(
    *,
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    notification_queue: FakeProjectNotificationQueue,
    monkeypatch: pytest.MonkeyPatch,
    project_collector: FakeProjectCollector,
    category_gateway: FakeProjectCategoryGateway,
):
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    enqueue = notification_queue.enqueue

    async def checking_enqueue(project_ids: list[UUID]) -> None:
        assert txn.commits == 1
        assert project_ids == [project_gateway.bulk_inserted[0].id]
        await enqueue(project_ids)

    monkeypatch.setattr(notification_queue, "enqueue", checking_enqueue)
    await sync_service.sync(Marketplace.FL)
    assert len(notification_queue.enqueued) == 1


@pytest.mark.asyncio
async def test_sync_empty_upsert_result(
    *,
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    notification_queue: FakeProjectNotificationQueue,
    monkeypatch: pytest.MonkeyPatch,
    project_collector: FakeProjectCollector,
    category_gateway: FakeProjectCategoryGateway,
):
    # Сохраняем транзакцию, но не ставим рассылки для пустого результата.
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    monkeypatch.setattr(
        project_gateway,
        "bulk_upsert",
        AsyncMock(return_value=[]),
    )
    assert await sync_service.sync(Marketplace.FL) == []
    assert txn.commits == 1
    assert notification_queue.enqueued == []


@pytest.mark.asyncio
async def test_sync_gateway_error(
    *,
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    notification_queue: FakeProjectNotificationQueue,
    monkeypatch: pytest.MonkeyPatch,
    project_collector: FakeProjectCollector,
    category_gateway: FakeProjectCategoryGateway,
):
    # Проверяет передачу ошибки сохранения проектов вызывающему коду без
    # фиксации транзакции.
    project_collector.source = Marketplace.FL
    project_collector.projects = [marketplace_project()]
    category_gateway.existing = [category()]
    sync_service.integrations = {
        Marketplace.FL: MarketplaceIntegration(project_collector),
    }

    monkeypatch.setattr(
        project_gateway,
        "bulk_upsert",
        AsyncMock(side_effect=RuntimeError("save")),
    )
    with pytest.raises(RuntimeError, match="save"):
        await sync_service.sync(Marketplace.FL)
    assert txn.commits == 0
    assert notification_queue.enqueued == []


@pytest.mark.asyncio
async def test_sync_lock_release_after_failure(
    sync_service: ProjectSyncService,
    project_collector: FakeProjectCollector,
    lock_manager: FakeDistributedLockManager,
    monkeypatch: pytest.MonkeyPatch,
):
    # Проверяет выход из контекста блокировки при ошибке сборщика с передачей
    # исключения вызывающему коду.
    project_collector.source = Marketplace.FL

    monkeypatch.setattr(
        project_collector,
        "collect",
        AsyncMock(side_effect=RuntimeError("collect")),
    )
    sync_service.integrations[Marketplace.FL] = MarketplaceIntegration(
        project_collector,
        LockOptions("fl-key", 20),
    )
    with pytest.raises(RuntimeError, match="collect"):
        await sync_service.sync(Marketplace.FL)
    assert lock_manager.enter_count == lock_manager.exit_count == 1


# ---------------------------------------------------------------------------
# _save_projects()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_saves_new_projects_with_mapped_categories(
    sync_service: ProjectSyncService,
    category_gateway: FakeProjectCategoryGateway,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
):
    # Проверяет сохранение полей новых проектов, сопоставление категорий с
    # внутренними ID и очистку HTML в описании.
    """Новые проекты сохраняются с категориями и исходными полями."""
    design = make_category("1", "Дизайн")
    dev = make_category("2", "Разработка")
    category_gateway.existing = [design, dev]
    projects = [
        make_project(
            "p1",
            "1",
            title="Логотип",
            description="<b>Срочно</b>",
            price=500,
            possible_price_limit=1000,
            has_exact_budget=True,
            offers=5,
        ),
        make_project("p2", "2"),
    ]

    result = await sync_service._save_projects(
        projects=projects,
        source=Marketplace.KWORK,
    )

    assert project_gateway.bulk_upsert_calls == 1
    assert txn.commits == 1
    assert result == [p.id for p in project_gateway.bulk_inserted]

    inserted = {p.external_id: p for p in project_gateway.bulk_inserted}
    p1 = inserted["p1"]
    assert isinstance(p1.id, UUID)
    assert p1.category_id == design.id
    assert p1.source == Marketplace.KWORK
    assert p1.title == "Логотип"
    assert p1.description == "Срочно"
    assert p1.price == 500
    assert p1.possible_price_limit == 1000
    assert p1.offers == 5
    assert inserted["p2"].category_id == dev.id


@pytest.mark.asyncio
async def test_empty_projects_do_not_access_gateways(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
):
    # Проверяет возврат пустого списка без сохранения проектов, заказчиков и
    # фиксации транзакции при пустом входе.
    """Пустой batch не вызывает gateway и не открывает транзакцию."""
    result = await sync_service._save_projects(
        projects=[],
        source=Marketplace.KWORK,
    )

    assert result == []
    assert project_gateway.bulk_upsert_calls == 0
    assert customer_gateway.upsert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_does_not_insert_when_all_projects_exist(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
):
    # Проверяет, что уже существующие проекты не вставляются повторно и не
    # вызывают сохранение заказчиков.
    """Уже существующие проекты и их заказчики не сохраняются повторно."""
    project_gateway.existing = [
        make_saved_project(
            external_id=external_id,
            source=Marketplace.KWORK,
            title="Title",
            description="Description",
            price=100,
        )
        for external_id in ("p1", "p2")
    ]

    result = await sync_service._save_projects(
        projects=[
            make_project("p1", "1"),
            make_project("p2", "2"),
        ],
        source=Marketplace.KWORK,
    )

    assert result == []
    assert customer_gateway.upsert_calls == 0
    assert project_gateway.bulk_upsert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_inserts_only_missing_projects_and_customers(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
):
    # Проверяет, что из смешанного списка сохраняются только новые проекты и их
    # заказчики.
    """Из смешанного batch сохраняются только новые проекты и заказчики."""
    project_gateway.existing = [
        make_saved_project(
            external_id="p1",
            source=Marketplace.KWORK,
            title="Title",
            description="Description",
            price=100,
        ),
    ]

    existing_customer = make_customer("c1")
    new_customer = make_customer("c2")

    result = await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=existing_customer),
            make_project("p2", "2", customer=new_customer),
        ],
        source=Marketplace.KWORK,
    )

    assert [
        project.external_id for project in project_gateway.bulk_inserted
    ] == ["p2"]

    assert [
        customer.external_id for customer in customer_gateway.upserted
    ] == ["c2"]

    assert result == [project.id for project in project_gateway.bulk_inserted]
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_missing_category_is_saved_as_none(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    caplog: pytest.LogCaptureFixture,
):
    # Проверяет сохранение проектов с отсутствующей или неизвестной категорией
    # без связи с ней и запись предупреждения.
    """Проект с неизвестной категорией сохраняется без связи с ней."""
    with caplog.at_level(logging.WARNING):
        result = await sync_service._save_projects(
            projects=[
                make_project("p1", "unknown"),
                make_project("p2", None),
            ],
            source=Marketplace.KWORK,
        )

    inserted = {
        project.external_id: project
        for project in project_gateway.bulk_inserted
    }

    assert inserted["p1"].category_id is None
    assert inserted["p2"].category_id is None
    assert "unknown" in caplog.text
    assert result == [inserted["p1"].id, inserted["p2"].id]


@pytest.mark.asyncio
async def test_rejects_projects_from_another_source(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
):
    # Проверяет отклонение проектов другой площадки до сохранения данных и
    # фиксации транзакции.
    """Проекты другого источника отклоняются до сохранения данных."""
    customer = make_customer("c1")

    with pytest.raises(ValueError, match="source"):
        await sync_service._save_projects(
            projects=[
                make_project("valid", "1", customer=customer),
                make_project(
                    "p1",
                    "1",
                    source=Marketplace.FL,
                    customer=customer,
                ),
            ],
            source=Marketplace.KWORK,
        )

    assert project_gateway.bulk_upsert_calls == 0
    assert customer_gateway.upsert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_deduplicates_projects_by_external_id(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
):
    # Проверяет, что проекты с одинаковым внешним ID сохраняются один раз с
    # данными первого вхождения.
    """Дубли проектов объединяются по external_id с правилом first wins."""
    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", title="Old"),
            make_project("p1", "1", title="New"),
            make_project("p2", "2"),
        ],
        source=Marketplace.KWORK,
    )

    assert [
        project.external_id for project in project_gateway.bulk_inserted
    ] == ["p1", "p2"]

    inserted = {
        project.external_id: project
        for project in project_gateway.bulk_inserted
    }
    assert inserted["p1"].title == "Old"


@pytest.mark.asyncio
async def test_deduplicates_customers_across_projects(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
):
    # Проверяет однократное сохранение заказчика с данными первого вхождения.
    """Один заказчик из нескольких проектов сохраняется один раз."""
    first = make_customer("c1", username="alice")
    second = make_customer("c1", username="bob")

    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=first),
            make_project("p2", "2", customer=second),
        ],
        source=Marketplace.KWORK,
    )

    assert customer_gateway.upsert_calls == 1
    assert len(customer_gateway.upserted) == 1
    assert customer_gateway.upserted[0].external_id == "c1"
    assert customer_gateway.upserted[0].username == "alice"


@pytest.mark.asyncio
async def test_maps_saved_customer_id_to_project(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
):
    # Проверяет сохранение данных заказчика и запись его внутреннего ID в
    # связанный проект.
    """Сохранённый UUID заказчика записывается во внешний ключ проекта."""
    customer = make_customer(
        "c1",
        username="ivan",
        user_projects_count=12,
        user_hired_percent=75,
    )
    customer.profile_picture = "avatar"

    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=customer),
        ],
        source=Marketplace.KWORK,
    )

    saved_customer = customer_gateway.upserted[0]
    saved_project = project_gateway.bulk_inserted[0]

    assert saved_customer.external_id == "c1"
    assert (
        saved_customer.username,
        saved_customer.profile_picture,
        saved_customer.user_projects_count,
        saved_customer.user_hired_percent,
    ) == ("ivan", "avatar", 12, 75)
    assert saved_project.customer_id == saved_customer.id


@pytest.mark.asyncio
async def test_project_without_customer_has_null_customer_id(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
):
    # Проверяет сохранение проекта без заказчика с customer_id=None без вызова
    # сохранения заказчиков.
    """Проект без заказчика сохраняется с customer_id=None."""
    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=None),
        ],
        source=Marketplace.KWORK,
    )

    assert customer_gateway.upsert_calls == 0
    assert project_gateway.bulk_inserted[0].customer_id is None


@pytest.mark.asyncio
async def test_multiple_distinct_customers_are_saved(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
):
    # Проверяет сохранение разных заказчиков из одного списка проектов за один
    # вызов шлюза.
    """Разные заказчики одного batch сохраняются одной bulk-операцией."""
    first = make_customer("c1", username="alice")
    second = make_customer("c2", username="bob")

    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=first),
            make_project("p2", "2", customer=second),
        ],
        source=Marketplace.KWORK,
    )

    assert customer_gateway.upsert_calls == 1
    assert {
        customer.external_id for customer in customer_gateway.upserted
    } == {"c1", "c2"}


# ---------------------------------------------------------------------------
# Нормализация описания
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "  Hello &amp; &lt;b&gt;World&lt;/b&gt;<br>line<br/>2   ",
            "Hello & World\nline\n2",
        ),
        ("a\n\n\n\nb", "a\n\nb"),
        ("a   b\t\tc", "a b c"),
        (
            "  Первый <b>важный</b> абзац<br><br>Второй &amp; третий  ",
            "Первый важный абзац\n\nВторой & третий",
        ),
    ],
)
def test_normalizes_project_description(
    sync_service: ProjectSyncService,
    description: str,
    expected: str,
):
    # Проверяет очистку описания от HTML, декодирование сущностей и сокращение
    # лишних пробелов и переносов строк.
    """Описание очищается от HTML и лишних пробелов и переносов."""
    assert sync_service._normalize_description(description) == expected
