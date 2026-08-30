from uuid import UUID, uuid7

import pytest

from fakes.infra import FakeTransactionManager
from fakes.projects import FakeMarketPlaceClient, FakeProjectCategoryGateway

from lansly.projects.consts import Marketplace
from lansly.projects.dto import MarketplaceCategory
from lansly.projects.models import ProjectCategory
from lansly.projects.services import ProjectCategoryService


@pytest.fixture
def category_service(
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
) -> ProjectCategoryService:
    return ProjectCategoryService(
        gateway=category_gateway,
        marketplace_clients=[marketplace_client],
        transaction_manager=txn,
    )


def category(
    external_id: str,
    title: str,
    source: str = Marketplace.KWORK,
    *subs: MarketplaceCategory,
) -> MarketplaceCategory:
    return MarketplaceCategory(
        id=external_id,
        source=source,
        title=title,
        subcategories=tuple(subs),
    )


@pytest.mark.asyncio
async def test_import_creates_new_categories_and_subcategories(
    category_service: ProjectCategoryService,
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
):
    marketplace_client.categories = [
        category(
            "1",
            "Дизайн",
            Marketplace.KWORK,
            MarketplaceCategory(
                id="10",
                source=Marketplace.KWORK,
                title="Логотипы",
            ),
            MarketplaceCategory(
                id="11",
                source=Marketplace.KWORK,
                title="Баннеры",
            ),
        ),
        category("2", "Разработка"),
    ]
    await category_service.import_categories()

    assert category_gateway.upsert_calls == 1
    assert txn.commits == 1

    by_external = {c.external_id: c for c in category_gateway.upserted}
    assert set(by_external) == {"1", "10", "11", "2"}

    design = by_external["1"]
    assert isinstance(design.id, UUID)
    assert design.parent_id is None
    assert design.source == Marketplace.KWORK
    assert design.title == "Дизайн"

    assert by_external["10"].parent_id == design.id
    assert by_external["11"].parent_id == design.id
    assert by_external["2"].parent_id is None


@pytest.mark.asyncio
async def test_import_reuses_existing_ids(
    category_service: ProjectCategoryService,
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    existing_id = uuid7()
    category_gateway.existing = [
        ProjectCategory(
            id=existing_id,
            external_id="1",
            source=Marketplace.KWORK,
            title="Старый заголовок",
            parent_id=None,
        ),
    ]
    marketplace_client.categories = [
        category(
            "1",
            "Дизайн",
            Marketplace.KWORK,
            MarketplaceCategory(
                id="10",
                source=Marketplace.KWORK,
                title="Логотипы",
            ),
        ),
    ]
    await category_service.import_categories()

    by_external = {c.external_id: c for c in category_gateway.upserted}
    assert by_external["1"].id == existing_id
    assert by_external["10"].parent_id == existing_id


@pytest.mark.asyncio
async def test_import_skips_categories_without_title(
    category_service: ProjectCategoryService,
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    marketplace_client.categories = [
        MarketplaceCategory(id="1", source=Marketplace.KWORK, title=""),
        MarketplaceCategory(
            id="2",
            source=Marketplace.KWORK,
            title="Разработка",
            subcategories=(
                MarketplaceCategory(
                    id="20",
                    source=Marketplace.KWORK,
                    title="",
                ),
            ),
        ),
    ]

    await category_service.import_categories()

    assert [c.external_id for c in category_gateway.upserted] == ["2"]


@pytest.mark.asyncio
async def test_import_handles_category_without_subcategories(
    category_service: ProjectCategoryService,
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    marketplace_client.categories = [category("1", "Разработка")]

    await category_service.import_categories()

    assert len(category_gateway.upserted) == 1
    assert category_gateway.upserted[0].parent_id is None


@pytest.mark.asyncio
async def test_import_empty_list_commits_without_categories(
    category_service: ProjectCategoryService,
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
    txn: FakeTransactionManager,
):
    marketplace_client.categories = []

    await category_service.import_categories()

    assert marketplace_client.get_categories_calls == 1
    assert category_gateway.upsert_calls == 0
    assert category_gateway.upserted == []
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_import_skips_duplicate_category_ids(
    category_service: ProjectCategoryService,
    category_gateway: FakeProjectCategoryGateway,
    marketplace_client: FakeMarketPlaceClient,
):
    marketplace_client.categories = [
        category(
            "1",
            "Дизайн",
            Marketplace.KWORK,
            MarketplaceCategory(
                id="10",
                source=Marketplace.KWORK,
                title="Логотипы",
            ),
        ),
        category(
            "2",
            "Разработка",
            Marketplace.KWORK,
            MarketplaceCategory(
                id="10",
                source=Marketplace.KWORK,
                title="Логотипы",
            ),
        ),
    ]
    await category_service.import_categories()
    by_external = {c.external_id: c for c in category_gateway.upserted}
    assert set(by_external) == {"1", "10", "2"}


@pytest.mark.asyncio
async def test_import_categories_from_multiple_sources(
    category_gateway: FakeProjectCategoryGateway,
    txn: FakeTransactionManager,
):
    kwork = FakeMarketPlaceClient(
        categories=[
            category("k1", "Kwork Cat", source=Marketplace.KWORK),
        ]
    )
    flru = FakeMarketPlaceClient(
        categories=[
            category("f1", "FlRu Cat", source=Marketplace.FLRU),
        ]
    )
    service = ProjectCategoryService(
        gateway=category_gateway,
        marketplace_clients=[kwork, flru],
        transaction_manager=txn,
    )

    await service.import_categories()

    assert category_gateway.upsert_calls == 2  # once per source
    by_ext = {c.external_id: c for c in category_gateway.upserted}
    assert by_ext["k1"].source == Marketplace.KWORK
    assert by_ext["f1"].source == Marketplace.FLRU
    assert txn.commits == 1


@pytest.mark.asyncio
async def test_same_external_id_different_sources_no_collision(
    category_gateway: FakeProjectCategoryGateway,
):
    kwork = FakeMarketPlaceClient(
        categories=[
            category("1", "Kwork Design", source=Marketplace.KWORK),
        ]
    )
    flru = FakeMarketPlaceClient(
        categories=[
            category("1", "FlRu Design", source=Marketplace.FLRU),
        ]
    )
    service = ProjectCategoryService(
        gateway=category_gateway,
        marketplace_clients=[kwork, flru],
        transaction_manager=FakeTransactionManager(),
    )

    await service.import_categories()

    by_ext = {c.external_id: c for c in category_gateway.upserted}
    assert len(by_ext) == 1  # same key
    # Последний upsert побеждает (flru)
    assert by_ext["1"].source == Marketplace.FLRU
    assert by_ext["1"].title == "FlRu Design"


@pytest.mark.asyncio
async def test_skips_duplicates_within_same_source(
    category_gateway: FakeProjectCategoryGateway,
):
    kwork = FakeMarketPlaceClient(
        categories=[
            category(
                "1",
                "Design",
                Marketplace.KWORK,
                MarketplaceCategory(
                    id="10",
                    title="Logos",
                    source=Marketplace.KWORK,
                ),
            ),
            category(
                "2",
                "Dev",
                Marketplace.KWORK,
                MarketplaceCategory(
                    id="10",
                    title="Logos",
                    source=Marketplace.KWORK,
                ),
            ),
        ],
    )
    service = ProjectCategoryService(
        gateway=category_gateway,
        marketplace_clients=[kwork],
        transaction_manager=FakeTransactionManager(),
    )

    await service.import_categories()

    by_ext = {c.external_id: c for c in category_gateway.upserted}
    assert set(by_ext) == {"1", "10", "2"}  # subcategory "10" only once
