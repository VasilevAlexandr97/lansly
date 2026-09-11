from uuid import uuid7

import pytest
import pytest_asyncio

from dishka import Provider, Scope, make_async_container
from taskiq import InMemoryBroker

from lansly.background_tasks import tasks
from lansly.projects.services import ProjectSyncService


class SyncService:
    def __init__(self):
        self.ids, self.calls = [], []
        self.error = None

    async def sync(self, source):
        self.calls.append(source)
        if self.error:
            raise self.error
        return self.ids


class RecordingBroker(InMemoryBroker):
    def __init__(self):
        super().__init__()
        self.messages = []

    async def kick(self, message):
        self.messages.append(self.formatter.loads(message.message))


def provide_sync_service(service):
    def factory():
        return service

    return factory


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    service, broker = SyncService(), RecordingBroker()
    provider = Provider()
    provider.provide(
        provide_sync_service(service),
        provides=ProjectSyncService,
        scope=Scope.APP,
    )
    container = make_async_container(provider)
    # Объекты задач глобальные: на время теста внедряем записывающий брокер.
    # Методы .kiq, сериализация и DI-обёртка остаются настоящими.
    for task in [
        tasks.notify_new_projects,
        tasks.notify_new_projects_to_channel,
    ]:
        monkeypatch.setattr(task, "broker", broker)
    yield service, broker, container
    await container.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["fl", "kwork"])
async def test_monitoring_source(ctx, source):
    # Проверяет, что задача мониторинга передаёт выбранную площадку сервису
    # синхронизации.
    service, _broker, container = ctx
    await tasks.monitoring_projects(source, dishka_container=container)
    assert service.calls == [source]


@pytest.mark.asyncio
async def test_monitoring_new_ids(ctx):
    # Проверяет постановку задач уведомления пользователей и канала с ID новых
    # проектов.
    service, broker, container = ctx
    service.ids = [uuid7(), uuid7()]
    await tasks.monitoring_projects("fl", dishka_container=container)
    assert [m.task_name for m in broker.messages] == [
        tasks.notify_new_projects.task_name,
        tasks.notify_new_projects_to_channel.task_name,
    ]
    assert all(
        m.args == [[str(uid) for uid in service.ids]] for m in broker.messages
    )


@pytest.mark.asyncio
async def test_monitoring_empty_ids(ctx):
    # Проверяет, что при отсутствии новых проектов задачи уведомления не
    # создаются.
    _service, broker, container = ctx
    await tasks.monitoring_projects("fl", dishka_container=container)
    assert broker.messages == []


@pytest.mark.asyncio
async def test_monitoring_sync_failure(ctx):
    # Проверяет, что ошибка синхронизации передаётся вызывающему коду, а
    # уведомления не планируются.
    service, broker, container = ctx
    service.error = RuntimeError("sync")
    with pytest.raises(RuntimeError, match="sync"):
        await tasks.monitoring_projects("fl", dishka_container=container)
    assert not broker.messages


def test_monitoring_schedules():
    # Проверяет отдельное ежеминутное расписание мониторинга для Kwork и FL.ru.
    assert tasks.monitoring_projects.labels["schedule"] == [
        {
            "cron": "* * * * *",
            "args": ["kwork"],
            "schedule_id": "projects-sync:kwork",
        },
        {
            "cron": "* * * * *",
            "args": ["fl"],
            "schedule_id": "projects-sync:fl",
        },
    ]
