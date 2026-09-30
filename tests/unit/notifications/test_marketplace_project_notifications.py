# ruff: noqa: PLR2004, SLF001
import logging

import pytest

from fakes.factories import (
    project as make_project,
    user as make_user,
)
from fakes.infra import (
    FakeDistributedLockManager,
    FakeTransactionManager,
    LockCall,
)
from fakes.notifications import (
    FakeChannelNotificationGateway,
    FakeProjectNotificationGateway,
    FakeTelegramNotifier,
)
from fakes.preferences import (
    FakeUserCategoryFollowGateway,
    FakeUserPriceFilterGateway,
    FakeUserStopWordsGateway,
)
from fakes.projects import FakeProjectGateway

from lansly.notifications.exceptions import RecipientUnavailableError
from lansly.notifications.services import ProjectNotificationService
from lansly.projects.models import Project
from lansly.users.models import User

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("source", "label", "url"),
    [
        ("fl", "FL", "https://fl.ru/projects/42/?ref=7"),
        ("kwork", "KWORK", "https://kwork.ru/projects/42?ref=8"),
    ],
)
async def test_user_marketplace_template(
    *,
    service: ProjectNotificationService,
    project: Project,
    notifier: FakeTelegramNotifier,
    source: str,
    label: str,
    url: str,
) -> None:
    # Проверяет, что уведомление пользователю содержит название площадки и
    # реферальную ссылку на проект.
    project.source = source
    await service.notify_new_projects([project.id])
    (sent,) = notifier.sent
    assert label in sent["text"]
    assert url in sent["text"]
    assert sent["chat_id"] == 123


async def test_user_project_keyboard(
    *,
    service: ProjectNotificationService,
    project: Project,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что кнопка проекта и текст уведомления содержат одну и ту же
    # реферальную ссылку.
    await service.notify_new_projects([project.id])
    (sent,) = notifier.sent
    links = [
        b.url for row in sent["keyboard"].inline_keyboard for b in row if b.url
    ]
    assert links == ["https://fl.ru/projects/42/?ref=7"]
    assert links[0] in sent["text"]


async def test_user_followed_category(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    follow_gateway: FakeUserCategoryFollowGateway,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет поиск получателей по категории проекта и отправку уведомления
    # найденному пользователю.
    await service.notify_new_projects([project.id])
    assert follow_gateway.requested_categories == [project.category_id]
    assert [s["chat_id"] for s in notifier.sent] == [user.telegram_id]


async def test_user_without_telegram(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    notification_gateway: FakeProjectNotificationGateway,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что пользователю без Telegram ID уведомление не отправляется и
    # запись об отправке не создаётся.
    user.telegram_id = None
    await service.notify_new_projects([project.id])
    assert not notifier.sent
    assert not notification_gateway.rows


async def test_user_without_category(
    *,
    service: ProjectNotificationService,
    project: Project,
    follow_gateway: FakeUserCategoryFollowGateway,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что для проекта без категории получатели не запрашиваются и
    # уведомления не отправляются.
    project.category_id = None
    await service.notify_new_projects([project.id])
    assert not notifier.sent
    assert not follow_gateway.requested_categories


@pytest.mark.parametrize("source", ["fl", "kwork"])
@pytest.mark.parametrize("word", ["ЛОГОТИП", "ПРОБЕЛАМИ"])
async def test_user_stop_words(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    stop_words_gateway: FakeUserStopWordsGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
    source: str,
    word: str,
) -> None:
    # Проверяет, что стоп-слова в верхнем регистре блокируют уведомления о
    # проектах обеих площадок.
    project.source = source
    stop_words_gateway.words[user.id] = [word]
    await service.notify_new_projects([project.id])
    assert not notifier.sent
    assert txn.commits == 0


@pytest.mark.parametrize("source", ["fl", "kwork"])
@pytest.mark.parametrize(
    ("price", "allowed"),
    [(99, False), (100, True), (200, True), (201, False)],
)
async def test_user_price_bounds(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    price_filter_gateway: FakeUserPriceFilterGateway,
    notifier: FakeTelegramNotifier,
    source: str,
    price: int,
    allowed: bool,
) -> None:
    # Проверяет, что ценовой фильтр допускает обе границы диапазона и исключает
    # цены за его пределами.
    project.source, project.price = source, price
    price_filter_gateway.prices[user.id] = (100, 200)
    await service.notify_new_projects([project.id])
    assert bool(notifier.sent) is allowed


async def test_user_negotiable_price_filter(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    price_filter_gateway: FakeUserPriceFilterGateway,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что проект с договорным бюджетом и нулевой ценой не проходит
    # фильтр с положительной нижней границей.
    project.price, project.has_exact_budget = 0, False
    price_filter_gateway.prices[user.id] = (1, 100)
    await service.notify_new_projects([project.id])
    assert not notifier.sent


async def test_user_without_filters(
    *,
    service: ProjectNotificationService,
    project: Project,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет отправку уведомления пользователю, у которого не заданы
    # фильтры.
    await service.notify_new_projects([project.id])
    assert len(notifier.sent) == 1


async def test_user_success_saved(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    notification_gateway: FakeProjectNotificationGateway,
    txn: FakeTransactionManager,
) -> None:
    # Проверяет сохранение ID проекта, ID получателя и времени успешной
    # отправки с фиксацией транзакции.
    await service.notify_new_projects([project.id])
    (row,) = notification_gateway.rows
    assert (row.project_id, row.user_id) == (project.id, user.id)
    assert row.sent_at is not None
    assert row.sent_at.tzinfo is not None
    assert row.error is None
    assert txn.commits == 1


async def test_user_send_failure(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    follow_gateway: FakeUserCategoryFollowGateway,
    notification_gateway: FakeProjectNotificationGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Проверяет, что сбой отправки одному пользователю не мешает уведомить
    # другого и сохранить его отправку.
    notifier.errors[user.telegram_id] = RuntimeError("Telegram unavailable")
    other = make_user(telegram_id=456)
    follow_gateway.users_by_category[project.category_id].append(other)
    await service.notify_new_projects([project.id])
    assert [s["chat_id"] for s in notifier.sent] == [456]
    failed, succeeded = notification_gateway.rows
    assert failed.user_id == user.id
    assert failed.sent_at is not None
    assert failed.error == "Telegram unavailable"
    assert succeeded.user_id == other.id
    assert succeeded.sent_at is not None
    assert succeeded.error is None
    assert not user.is_telegram_unavailable
    assert txn.commits == 1
    assert any(
        record.name == "lansly.notifications.services"
        and record.levelno == logging.ERROR
        and record.exc_info is not None
        for record in caplog.records
    )


@pytest.mark.parametrize("empty_projects", [True, False])
async def test_user_no_deliveries(
    *,
    service: ProjectNotificationService,
    project: Project,
    follow_gateway: FakeUserCategoryFollowGateway,
    notification_gateway: FakeProjectNotificationGateway,
    txn: FakeTransactionManager,
    empty_projects: bool,
) -> None:
    # Проверяет, что без проектов или получателей записи об отправке не
    # создаются и транзакция не фиксируется.
    follow_gateway.users_by_category.clear()
    await service.notify_new_projects([] if empty_projects else [project.id])
    assert not notification_gateway.rows
    assert txn.commits == 0


async def test_user_lock(
    *,
    service: ProjectNotificationService,
    project: Project,
    lock_manager: FakeDistributedLockManager,
) -> None:
    # Проверяет получение и освобождение блокировки при отправке уведомлений
    # пользователям.
    await service.notify_new_projects([project.id])
    assert lock_manager.calls == [
        LockCall(
            key="project_notification",
            timeout=600,
            blocking=True,
            blocking_timeout=None,
        ),
    ]
    assert lock_manager.enter_count == lock_manager.exit_count == 1


@pytest.mark.parametrize(
    ("source", "label"),
    [("fl", "FL"), ("kwork", "KWORK")],
)
async def test_channel_marketplace_template(
    *,
    service: ProjectNotificationService,
    project: Project,
    channel_notification_gateway: FakeChannelNotificationGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
    source: str,
    label: str,
) -> None:
    # Проверяет отправку в канал шаблона нужной площадки с согласованными
    # ссылками и сохранением результата.
    project.source = source
    await service.notify_new_projects_to_channel([project.id])
    (sent,) = notifier.sent
    assert sent["chat_id"] == -100
    assert label in sent["text"]
    assert sent["keyboard"].inline_keyboard[0][0].url in sent["text"]
    assert channel_notification_gateway.rows[0].project_id == project.id
    assert txn.commits == 1


async def test_channel_disabled(
    *,
    service: ProjectNotificationService,
    project: Project,
    project_gateway: FakeProjectGateway,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что при отключённом канале проекты не запрашиваются и
    # уведомления не отправляются.
    service.channel_id = None
    await service.notify_new_projects_to_channel([project.id])
    assert not project_gateway.get_projects_by_ids_calls
    assert not notifier.sent


@pytest.mark.parametrize(
    ("price", "allowed"),
    [(29999, False), (30000, True), (30001, True)],
)
async def test_channel_price_threshold(
    *,
    service: ProjectNotificationService,
    project: Project,
    notifier: FakeTelegramNotifier,
    price: int,
    allowed: bool,
) -> None:
    # Проверяет, что в канал попадают проекты с ценой от 30 000 рублей
    # включительно.
    project.price = price
    await service.notify_new_projects_to_channel([project.id])
    assert bool(notifier.sent) is allowed


async def test_channel_without_category(
    *,
    service: ProjectNotificationService,
    project: Project,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что проект без категории не отправляется в канал.
    project.category_id = None
    await service.notify_new_projects_to_channel([project.id])
    assert not notifier.sent


async def test_channel_send_failure(
    *,
    service: ProjectNotificationService,
    project: Project,
    project_gateway: FakeProjectGateway,
    channel_notification_gateway: FakeChannelNotificationGateway,
    notifier: FakeTelegramNotifier,
) -> None:
    # Проверяет, что после ошибки отправки первого проекта в канал второй
    # отправляется и сохраняется.
    # Ошибка отправки первого проекта не мешает отправке второго.
    notifier.fail_next = 1
    other = make_project()
    project_gateway.bulk_inserted.append(other)
    await service.notify_new_projects_to_channel([project.id, other.id])
    assert len(notifier.sent) == 1
    assert [r.project_id for r in channel_notification_gateway.rows] == [
        other.id,
    ]


async def test_channel_no_deliveries(
    *,
    service: ProjectNotificationService,
    project: Project,
    channel_notification_gateway: FakeChannelNotificationGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
) -> None:
    # Проверяет, что при неудачной отправке в канал запись об уведомлении не
    # создаётся и транзакция не фиксируется.
    notifier.errors[-100] = RuntimeError("Telegram unavailable")
    await service.notify_new_projects_to_channel([project.id])
    assert not channel_notification_gateway.rows
    assert txn.commits == 0


async def test_unsupported_source(
    *,
    service: ProjectNotificationService,
    project: Project,
) -> None:
    # Проверяет, что построение сообщения для неподдерживаемой площадки
    # вызывает ValueError.
    project.source = "unknown"
    with pytest.raises(ValueError, match="not supported"):
        service._get_project_message(project, None)


async def test_user_already_unavailable(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    notification_gateway: FakeProjectNotificationGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
) -> None:
    # Проверяет, что помеченному пользователю отправка не выполняется.
    user.is_telegram_unavailable = True
    await service.notify_new_projects([project.id])
    assert not notifier.attempts
    assert not notification_gateway.rows
    assert txn.commits == 0


async def test_user_becomes_unavailable(
    *,
    service: ProjectNotificationService,
    project: Project,
    user: User,
    project_gateway: FakeProjectGateway,
    notification_gateway: FakeProjectNotificationGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Проверяет сохранение ошибки, пропуск следующего проекта и отсутствие
    # ERROR-лога для ожидаемой недоступности получателя.
    previous_updated_at = user.updated_at
    other = make_project(category=project.category)
    project_gateway.bulk_inserted.append(other)
    notifier.errors[user.telegram_id] = RecipientUnavailableError(
        "Forbidden: bot was blocked by the user",
    )
    await service.notify_new_projects([project.id, other.id])
    assert [attempt["chat_id"] for attempt in notifier.attempts] == [
        user.telegram_id,
    ]
    assert not notifier.sent
    (failed,) = notification_gateway.rows
    assert (failed.project_id, failed.user_id) == (project.id, user.id)
    assert failed.sent_at is not None
    assert failed.error == "Forbidden: bot was blocked by the user"
    assert user.is_telegram_unavailable
    assert user.updated_at > previous_updated_at
    assert txn.commits == 1
    assert not any(
        record.name == "lansly.notifications.services"
        and record.levelno >= logging.ERROR
        for record in caplog.records
    )


async def test_user_lock_not_acquired(
    *,
    service: ProjectNotificationService,
    project: Project,
    lock_manager: FakeDistributedLockManager,
    notifier: FakeTelegramNotifier,
    notification_gateway: FakeProjectNotificationGateway,
    txn: FakeTransactionManager,
) -> None:
    lock_manager.acquired = False
    with pytest.raises(RuntimeError, match="lock was not acquired"):
        await service.notify_new_projects([project.id])
    assert not notifier.attempts
    assert not notification_gateway.rows
    assert txn.commits == 0
    assert lock_manager.enter_count == lock_manager.exit_count == 1
