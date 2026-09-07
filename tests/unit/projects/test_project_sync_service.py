import logging

from uuid import UUID, uuid7

import pytest

from fakes.infra import (
    FakeDistributedLockManager,
    FakeTransactionManager,
    LockCall,
)
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


@pytest.fixture
def sync_service(
    category_gateway: FakeProjectCategoryGateway,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
) -> ProjectSyncService:
    return ProjectSyncService(
        integrations=[],
        category_gateway=category_gateway,
        project_gateway=project_gateway,
        customer_gateway=customer_gateway,
        transaction_manager=txn,
        lock_manager=lock_manager,
    )


# ---------------------------------------------------------------------------
# sync()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_without_lock_collects_and_saves_projects(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
):
    """Интеграция без lock собирает и сохраняет проекты напрямую."""
    collector = FakeProjectCollector(
        source=Marketplace.KWORK,
        projects=[make_project("p1", "1")],
    )
    integration = MarketplaceIntegration(
        collector=collector,
        lock=None,
    )
    sync_service.integrations = {Marketplace.KWORK: integration}

    result = await sync_service.sync(Marketplace.KWORK)

    assert collector.collect_calls == 1
    assert lock_manager.calls == []
    assert project_gateway.bulk_insert_calls == 1
    assert txn.commits == 1
    assert result == [project.id for project in project_gateway.bulk_inserted]


@pytest.mark.asyncio
async def test_sync_with_acquired_lock_collects_and_saves_projects(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
):
    """При полученном lock синхронизация выполняется с его настройками."""
    collector = FakeProjectCollector(
        source=Marketplace.FL,
        projects=[
            make_project(
                "p1",
                "1",
                source=Marketplace.FL,
            ),
        ],
    )
    lock = LockOptions(
        key="projects:sync:fl",
        timeout=300,
        blocking=True,
        blocking_timeout=5,
    )
    integration = MarketplaceIntegration(
        collector=collector,
        lock=lock,
    )
    sync_service.integrations = {Marketplace.FL: integration}
    result = await sync_service.sync(Marketplace.FL)

    assert collector.collect_calls == 1
    assert project_gateway.bulk_insert_calls == 1
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
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
):
    """При занятом lock синхронизация не запускает collector."""
    lock_manager.acquired = False
    collector = FakeProjectCollector(
        source=Marketplace.FL,
        projects=[
            make_project(
                "p1",
                "1",
                source=Marketplace.FL,
            ),
        ],
    )
    lock = LockOptions(
        key="projects:sync:fl",
        timeout=300,
        blocking=False,
    )
    integration = MarketplaceIntegration(
        collector=collector,
        lock=lock,
    )
    sync_service.integrations = {Marketplace.FL: integration}

    result = await sync_service.sync(Marketplace.FL)

    assert result == []
    assert collector.collect_calls == 0
    assert project_gateway.bulk_insert_calls == 0
    assert customer_gateway.upsert_calls == 0
    assert txn.commits == 0

    assert lock_manager.enter_count == 1
    assert lock_manager.exit_count == 1


@pytest.mark.asyncio
async def test_sync_raises_when_integration_not_found(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
):
    """Для незарегистрированного источника выбрасывается исключение."""
    with pytest.raises(MarketplaceIntegrationNotFoundError):
        await sync_service.sync(Marketplace.KWORK)

    assert project_gateway.bulk_insert_calls == 0


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

    assert project_gateway.bulk_insert_calls == 1
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
    """Пустой batch не вызывает gateway и не открывает транзакцию."""
    result = await sync_service._save_projects(
        projects=[],
        source=Marketplace.KWORK,
    )

    assert result == []
    assert project_gateway.bulk_insert_calls == 0
    assert customer_gateway.upsert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_does_not_insert_when_all_projects_exist(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
):
    """Уже существующие проекты и их заказчики не сохраняются повторно."""
    project_gateway.existing_external_ids = {"p1", "p2"}

    result = await sync_service._save_projects(
        projects=[
            make_project("p1", "1"),
            make_project("p2", "2"),
        ],
        source=Marketplace.KWORK,
    )

    assert result == []
    assert customer_gateway.upsert_calls == 0
    assert project_gateway.bulk_insert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_inserts_only_missing_projects_and_customers(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
):
    """Из смешанного batch сохраняются только новые проекты и заказчики."""
    project_gateway.existing_external_ids = {"p1"}

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
    """Проекты другого источника отклоняются до сохранения данных."""
    customer = make_customer("c1")

    with pytest.raises(ValueError, match="source"):
        await sync_service._save_projects(
            projects=[
                make_project(
                    "p1",
                    "1",
                    source=Marketplace.FL,
                    customer=customer,
                ),
            ],
            source=Marketplace.KWORK,
        )

    assert project_gateway.bulk_insert_calls == 0
    assert customer_gateway.upsert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_deduplicates_projects_by_external_id(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
):
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
    """Один заказчик из нескольких проектов сохраняется один раз."""
    customer = make_customer("c1")

    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=customer),
            make_project("p2", "2", customer=customer),
        ],
        source=Marketplace.KWORK,
    )

    assert customer_gateway.upsert_calls == 1
    assert len(customer_gateway.upserted) == 1
    assert customer_gateway.upserted[0].external_id == "c1"


@pytest.mark.asyncio
async def test_maps_saved_customer_id_to_project(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
):
    """Сохранённый UUID заказчика записывается во внешний ключ проекта."""
    customer = make_customer("c1", username="ivan")

    await sync_service._save_projects(
        projects=[
            make_project("p1", "1", customer=customer),
        ],
        source=Marketplace.KWORK,
    )

    saved_customer = customer_gateway.upserted[0]
    saved_project = project_gateway.bulk_inserted[0]

    assert saved_customer.external_id == "c1"
    assert saved_customer.username == "ivan"
    assert saved_project.customer_id == saved_customer.id


@pytest.mark.asyncio
async def test_project_without_customer_has_null_customer_id(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
):
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
    ],
)
def test_normalizes_project_description(
    sync_service: ProjectSyncService,
    description: str,
    expected: str,
):
    """Описание очищается от HTML и лишних пробелов и переносов."""
    assert sync_service._normalize_description(description) == expected
