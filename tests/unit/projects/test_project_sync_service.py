from uuid import UUID, uuid7

import pytest

from fakes.infra import FakeTransactionManager
from fakes.projects import (
    FakeMarketPlaceClient,
    FakeProjectCategoryGateway,
    FakeProjectGateway,
)

from lansly.projects.dto import MarketPlaceProject
from lansly.projects.models import ProjectCategory, ProjectSource
from lansly.projects.services import ProjectSyncService


def make_project(
    external_id: str,
    category_id: str | None,
    *,
    title: str = "Title",
    description: str = "Description",
    price: int = 100,
    possible_price_limit: int = 200,
    offers: int = 3,
) -> MarketPlaceProject:
    return MarketPlaceProject(
        id=external_id,
        category_id=category_id,
        price=price,
        possible_price_limit=possible_price_limit,
        title=title,
        description=description,
        offers=offers,
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
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
) -> ProjectSyncService:
    return ProjectSyncService(
        category_gateway=category_gateway,
        project_gateway=project_gateway,
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
