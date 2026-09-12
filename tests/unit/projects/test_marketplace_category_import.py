# ruff: noqa: PLR2004
from uuid import uuid7

import pytest

from fakes.factories import category
from fakes.projects import FakeMarketPlaceClient, FakeProjectCategoryGateway

from lansly.projects.dto import MarketplaceCategory as Category
from lansly.projects.services import ProjectCategoryService

pytestmark = pytest.mark.asyncio


class MemoryCategories(FakeProjectCategoryGateway):
    async def upsert(self, categories):
        await super().upsert(categories)
        by_id = {c.id: c for c in self.existing}
        by_id.update({c.id: c for c in categories})
        self.existing = list(by_id.values())


@pytest.fixture
def gateway():
    return MemoryCategories()


def service(gateway, txn, *categories):
    return ProjectCategoryService(
        [FakeMarketPlaceClient(categories=items) for items in categories],
        gateway,
        txn,
    )


async def test_import_both_sources(gateway, txn):
    # Проверяет импорт категорий Kwork и FL.ru за один запуск с общей фиксацией
    # транзакции.
    await service(
        gateway,
        txn,
        [Category("1", "kwork", "K")],
        [Category("2", "fl", "F")],
    ).import_categories()
    assert {(c.source, c.title) for c in gateway.existing} == {
        ("kwork", "K"),
        ("fl", "F"),
    }
    assert txn.commits == 1


async def test_import_same_external_ids(gateway, txn):
    # Проверяет, что категории разных площадок с одинаковым внешним ID получают
    # разные внутренние ID.
    await service(
        gateway,
        txn,
        [Category("1", "kwork", "K")],
        [Category("1", "fl", "F")],
    ).import_categories()
    assert len({c.id for c in gateway.existing}) == 2


async def test_import_repeat(gateway, txn):
    # Проверяет, что повторный импорт сохраняет ID категорий, обновляет
    # названия и переносит подкатегорию к новому родителю.
    client = FakeMarketPlaceClient(
        categories=[
            Category("root", "fl", "Old", (Category("child", "fl", "Child"),)),
        ],
    )
    s = ProjectCategoryService([client], gateway, txn)
    await s.import_categories()
    ids = {c.external_id: c.id for c in gateway.existing}
    client.categories = [
        Category(
            "new-root",
            "fl",
            "New",
            (Category("child", "fl", "Renamed"),),
        ),
        Category("root", "fl", "Updated"),
    ]
    await s.import_categories()
    rows = {c.external_id: c for c in gateway.existing}
    assert rows["child"].id == ids["child"]
    assert rows["root"].id == ids["root"]
    assert rows["child"].title == "Renamed"
    assert rows["root"].title == "Updated"
    assert rows["child"].parent_id == rows["new-root"].id


async def test_import_duplicate_children(gateway, txn):
    # Проверяет, что повторяющаяся подкатегория импортируется один раз.
    child = Category("child", "fl", "Child")
    await service(
        gateway,
        txn,
        [Category("root", "fl", "Root", (child, child))],
    ).import_categories()
    assert len(gateway.existing) == 2


async def test_import_empty_children_titles(gateway, txn):
    # Проверяет, что подкатегория с пустым названием пропускается, а её
    # родитель сохраняется.
    await service(
        gateway,
        txn,
        [Category("root", "fl", "Root", (Category("child", "fl", ""),))],
    ).import_categories()
    assert len(gateway.existing) == 1


@pytest.mark.parametrize("clients", [[], [FakeMarketPlaceClient()]])
async def test_import_empty_clients(gateway, txn, clients):
    # Проверяет отсутствие записи и фиксации транзакции, когда нет клиентов или
    # они не вернули категории.
    await ProjectCategoryService(clients, gateway, txn).import_categories()
    assert not gateway.upserted
    assert txn.commits == 0


async def test_import_one_empty_source(gateway, txn):
    # Проверяет импорт категорий непустой площадки, когда другая площадка
    # вернула пустой список.
    await service(
        gateway,
        txn,
        [],
        [Category("1", "fl", "F")],
    ).import_categories()
    assert len(gateway.existing) == 1
    assert txn.commits == 1


async def test_import_fetch_error(gateway, txn):
    # Проверяет, что ошибка загрузки категорий прерывает импорт до записи и
    # фиксации транзакции.
    class FailingClient:
        async def get_categories(self):
            raise RuntimeError("fetch")

    with pytest.raises(RuntimeError, match="fetch"):
        await ProjectCategoryService(
            [
                FakeMarketPlaceClient([Category("1", "fl", "F")]),
                FailingClient(),
            ],
            gateway,
            txn,
        ).import_categories()
    assert not gateway.upserted
    assert txn.commits == 0


async def test_import_gateway_error(txn):
    # Проверяет передачу ошибки сохранения категорий вызывающему коду без
    # фиксации транзакции.
    class FailingGateway(MemoryCategories):
        async def upsert(self, categories):
            del categories
            raise RuntimeError("save")

    with pytest.raises(RuntimeError, match="save"):
        await service(
            FailingGateway(),
            txn,
            [Category("1", "fl", "F")],
        ).import_categories()
    assert txn.commits == 0


async def test_root_source_filter(gateway, txn):
    # Проверяет возврат корневых категорий только указанной площадки.
    gateway.existing = [category(source="fl"), category(source="kwork")]
    assert await service(gateway, txn).get_root_categories("fl") == [
        gateway.existing[0],
    ]


async def test_root_without_source(gateway, txn):
    # Проверяет возврат корневых категорий обеих площадок, если фильтр по
    # площадке не задан.
    gateway.existing = [category(source="fl"), category(source="kwork")]
    assert len(await service(gateway, txn).get_root_categories()) == 2


async def test_subcategories_parent_filter(gateway, txn):
    # Проверяет возврат подкатегорий только указанного родителя.
    root = uuid7()
    gateway.existing = [category(parent_id=root), category(parent_id=uuid7())]
    assert await service(gateway, txn).get_subcategories(root) == [
        gateway.existing[0],
    ]
