from time import monotonic

import pytest

from fakes.factories import marketplace_project

from lansly.projects.collectors import (
    FlRuProjectCollector,
    KworkProjectCollector,
)

pytestmark = pytest.mark.asyncio


class Client:
    def __init__(self, projects=(), details=None, error=None):
        self.projects = list(projects)
        self.details = details or {}
        self.error = error
        self.calls = []

    async def get_projects(self):
        if self.error:
            raise self.error
        return self.projects

    async def get_project(self, project_id):
        self.calls.append(project_id)
        result = self.details.get(project_id)
        if isinstance(result, Exception):
            raise result
        return result


class Gateway:
    def __init__(self, missing=()):
        self.missing = set(missing)
        self.calls = []

    async def get_missing_external_ids(self, **kwargs):
        self.calls.append(kwargs)
        return self.missing


async def test_kwork_collect():
    # Проверяет, что сборщик Kwork возвращает список клиента без отдельных
    # запросов карточек проектов.
    p = marketplace_project(source="kwork")
    client = Client([p])
    assert await KworkProjectCollector(client).collect() == [p]
    assert client.calls == []


async def test_kwork_collect_error():
    # Проверяет передачу ошибки загрузки списка проектов Kwork вызывающему
    # коду.
    with pytest.raises(RuntimeError, match="list"):
        await KworkProjectCollector(
            Client(error=RuntimeError("list")),
        ).collect()


async def test_fl_collect_new_projects():
    # Проверяет загрузку и возврат полных карточек только новых проектов FL.ru.
    p = marketplace_project()
    full = marketplace_project(description="Full")
    client = Client([p, marketplace_project(id="old")], {"42": full})
    assert await FlRuProjectCollector(client, Gateway(["42"])).collect() == [
        full,
    ]
    assert client.calls == ["42"]


async def test_fl_existing_projects():
    # Проверяет, что для уже известных проектов FL.ru карточки не запрашиваются
    # и результат пуст.
    client = Client([marketplace_project()])
    assert await FlRuProjectCollector(client, Gateway()).collect() == []
    assert not client.calls


async def test_fl_source_filter():
    # Проверяет передачу внешних ID и источника fl при поиске новых проектов.
    gateway = Gateway()
    await FlRuProjectCollector(
        Client([marketplace_project()]),
        gateway,
    ).collect()
    assert gateway.calls == [{"external_ids": ["42"], "source": "fl"}]


async def test_fl_empty_discovery():
    # Проверяет возврат пустого списка без запросов карточек, когда FL.ru не
    # вернул проекты.
    client = Client()
    assert await FlRuProjectCollector(client, Gateway()).collect() == []
    assert not client.calls


async def test_fl_unavailable_details():
    # Проверяет пропуск недоступной карточки FL.ru с продолжением загрузки
    # следующего проекта.
    p = marketplace_project(id="43")
    client = Client([marketplace_project(), p], {"43": p})
    assert await FlRuProjectCollector(
        client,
        Gateway(["42", "43"]),
    ).collect() == [p]
    assert client.calls == ["42", "43"]


async def test_fl_delay():
    # Проверяет, что сбор одной карточки FL.ru включает паузу не короче одной
    # секунды.
    # Проверяем настоящую минимальную паузу без патча asyncio.
    client = Client([marketplace_project()])
    started = monotonic()
    await FlRuProjectCollector(client, Gateway(["42"])).collect()
    assert monotonic() - started >= 1


async def test_fl_detail_error():
    # Проверяет передачу ошибки загрузки карточки FL.ru после запроса её ID.
    client = Client([marketplace_project()], {"42": RuntimeError("detail")})
    with pytest.raises(RuntimeError, match="detail"):
        await FlRuProjectCollector(client, Gateway(["42"])).collect()
    assert client.calls == ["42"]


async def test_fl_discovery_error():
    # Проверяет, что ошибка загрузки списка FL.ru передаётся вызывающему коду
    # до запросов карточек.
    client = Client(error=RuntimeError("list"))
    with pytest.raises(RuntimeError, match="list"):
        await FlRuProjectCollector(client, Gateway()).collect()
    assert client.calls == []
