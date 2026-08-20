from uuid import UUID, uuid7

import pytest

from fakes.infra import FakeTransactionManager
from fakes.projects import (
    FakeCustomerGateway,
    FakeMarketPlaceClient,
    FakeProjectCategoryGateway,
    FakeProjectGateway,
)

from lansly.projects.dto import MarketPlaceCustomer, MarketPlaceProject
from lansly.projects.models import ProjectCategory, ProjectSource
from lansly.projects.services import ProjectSyncService


def make_customer(
    external_id: str,
    *,
    username: str | None = "testuser",
    user_projects_count: int | None = 10,
    user_hired_percent: int | None = 50,
) -> MarketPlaceCustomer:
    return MarketPlaceCustomer(
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
    description: str = "Description",
    price: int = 100,
    possible_price_limit: int = 200,
    offers: int = 3,
    customer: MarketPlaceCustomer | None = None,
) -> MarketPlaceProject:
    return MarketPlaceProject(
        id=external_id,
        category_id=category_id,
        price=price,
        possible_price_limit=possible_price_limit,
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
        source=ProjectSource.KWORK,
        title=title,
        parent_id=None,
    )


@pytest.fixture
def sync_service(
    category_gateway: FakeProjectCategoryGateway,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
) -> ProjectSyncService:
    return ProjectSyncService(
        category_gateway=category_gateway,
        project_gateway=project_gateway,
        customer_gateway=customer_gateway,
        marketplace_client=marketplace_client,
        transaction_manager=txn,
    )


@pytest.mark.asyncio
async def test_saves_new_projects_with_mapped_categories(
    sync_service: ProjectSyncService,
    category_gateway: FakeProjectCategoryGateway,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
):
    design = make_category("1", "Дизайн")
    dev = make_category("2", "Разработка")
    category_gateway.existing = [design, dev]
    marketplace_client.projects = [
        make_project(
            "p1",
            "1",
            title="Логотип",
            description="<b>Срочно</b>",
            price=500,
        ),
        make_project("p2", "2"),
    ]

    result = await sync_service.get_and_save_new_projects()

    assert project_gateway.bulk_insert_calls == 1
    assert txn.commits == 1
    assert result == [p.id for p in project_gateway.bulk_inserted]

    inserted = {p.external_id: p for p in project_gateway.bulk_inserted}
    p1 = inserted["p1"]
    assert isinstance(p1.id, UUID)
    assert p1.category_id == design.id
    assert p1.source == ProjectSource.KWORK
    assert p1.title == "Логотип"
    assert p1.description == "Срочно"
    assert p1.price == 500
    assert p1.possible_price_limit == 200
    assert p1.offers == 3
    assert inserted["p2"].category_id == dev.id


@pytest.mark.asyncio
async def test_does_not_insert_when_all_projects_exist(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
):
    project_gateway.existing_external_ids = {"p1", "p2"}
    marketplace_client.projects = [
        make_project("p1", "1"),
        make_project("p2", "2"),
    ]

    result = await sync_service.get_and_save_new_projects()

    assert result == []
    assert project_gateway.bulk_insert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_inserts_only_missing_projects(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
):
    project_gateway.existing_external_ids = {"p1"}
    marketplace_client.projects = [
        make_project("p1", "1"),
        make_project("p2", "2"),
    ]

    result = await sync_service.get_and_save_new_projects()

    assert [p.external_id for p in project_gateway.bulk_inserted] == ["p2"]
    assert result == [p.id for p in project_gateway.bulk_inserted]
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_missing_categories_map_to_none_and_log_warning(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
    caplog,
):
    marketplace_client.projects = [
        make_project("p1", "999"),
        make_project("p2", None),
    ]

    result = await sync_service.get_and_save_new_projects()

    inserted = {p.external_id: p for p in project_gateway.bulk_inserted}
    assert inserted["p1"].category_id is None
    assert inserted["p2"].category_id is None
    assert "999" in caplog.text
    assert result == [p.id for p in project_gateway.bulk_inserted]


@pytest.mark.asyncio
async def test_inserts_each_project_once_when_duplicates_in_page(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    marketplace_client.projects = [
        make_project("p1", "1"),
        make_project("p1", "1"),
        make_project("p2", "2"),
    ]
    result = await sync_service.get_and_save_new_projects()
    assert [p.external_id for p in project_gateway.bulk_inserted] == [
        "p1",
        "p2",
    ]
    assert result == [p.id for p in project_gateway.bulk_inserted]


@pytest.mark.asyncio
async def test_empty_projects_list(
    sync_service: ProjectSyncService,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
):
    marketplace_client.projects = []

    result = await sync_service.get_and_save_new_projects()

    assert result == []
    assert project_gateway.bulk_insert_calls == 0
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_upserts_customer_from_project(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    customer = make_customer("c1", username="ivan")
    marketplace_client.projects = [
        make_project("p1", "1", customer=customer),
    ]

    await sync_service.get_and_save_new_projects()

    assert customer_gateway.upsert_calls == 1
    assert len(customer_gateway.upserted) == 1
    assert customer_gateway.upserted[0].external_id == "c1"
    assert customer_gateway.upserted[0].username == "ivan"
    assert project_gateway.bulk_inserted[0].customer_id is not None


@pytest.mark.asyncio
async def test_deduplicates_customers_across_projects(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    customer = make_customer("c1")
    marketplace_client.projects = [
        make_project("p1", "1", customer=customer),
        make_project("p2", "2", customer=customer),
    ]

    await sync_service.get_and_save_new_projects()

    assert customer_gateway.upsert_calls == 1
    assert len(customer_gateway.upserted) == 1


@pytest.mark.asyncio
async def test_maps_customer_id_to_project(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    customer = make_customer("c1")
    marketplace_client.projects = [
        make_project("p1", "1", customer=customer),
    ]

    await sync_service.get_and_save_new_projects()

    project = project_gateway.bulk_inserted[0]
    upserted_customer = customer_gateway.upserted[0]
    assert project.customer_id == upserted_customer.id


@pytest.mark.asyncio
async def test_project_without_customer_gets_null_id(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    marketplace_client.projects = [
        make_project("p1", "1", customer=None),
    ]

    await sync_service.get_and_save_new_projects()

    assert customer_gateway.upsert_calls == 0
    assert project_gateway.bulk_inserted[0].customer_id is None


@pytest.mark.asyncio
async def test_multiple_distinct_customers(
    sync_service: ProjectSyncService,
    customer_gateway: FakeCustomerGateway,
    project_gateway: FakeProjectGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    c1 = make_customer("c1", username="alice")
    c2 = make_customer("c2", username="bob")
    marketplace_client.projects = [
        make_project("p1", "1", customer=c1),
        make_project("p2", "2", customer=c2),
    ]

    await sync_service.get_and_save_new_projects()

    assert customer_gateway.upsert_calls == 1
    assert len(customer_gateway.upserted) == 2
    ids = {c.external_id for c in customer_gateway.upserted}
    assert ids == {"c1", "c2"}


def test_clean_description_unescapes_and_removes_html(
    sync_service: ProjectSyncService,
):
    assert (
        sync_service._clean_project_description(
            "  Hello &amp; &lt;b&gt;World&lt;/b&gt;<br>line<br/>2   ",
        )
        == "Hello & World\nline\n2"
    )


def test_clean_description_normalizes_newlines(
    sync_service: ProjectSyncService,
):
    assert sync_service._clean_project_description("a\n\n\n\nb") == "a\n\nb"


def test_clean_description_collapses_spaces(sync_service: ProjectSyncService):
    assert sync_service._clean_project_description("a   b\t\tc") == "a b c"
