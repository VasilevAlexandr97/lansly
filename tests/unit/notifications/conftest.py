import pytest

from fakes.factories import (
    project as make_project,
    user as make_user,
)
from fakes.infra import FakeTransactionManager
from fakes.notifications import (
    FakeChannelNotificationGateway,
    FakeProjectNotificationGateway,
    FakeTelegramNotifier,
)
from fakes.preferences import (
    FakeUserPriceFilterGateway,
    FakeUserStopWordsGateway,
)
from fakes.projects import FakeProjectGateway

from lansly.infra.fl.urls import FLUrlStrategy
from lansly.infra.kwork.urls import KworkUrlStrategy
from lansly.notifications.services import ProjectNotificationService
from lansly.projects.models import Project
from lansly.projects.urls import MarketplaceUrlBuilder
from lansly.users.models import User


@pytest.fixture(autouse=True)
def project(project_gateway: FakeProjectGateway) -> Project:
    project = make_project()
    project_gateway.bulk_inserted.append(project)
    return project


@pytest.fixture(autouse=True)
def user(
    project: Project,
    notification_gateway: FakeProjectNotificationGateway,
) -> User:
    user = make_user()
    assert project.category_id is not None
    notification_gateway.users_by_category[project.category_id] = [user]
    return user


@pytest.fixture
def service(
    *,
    project_gateway: FakeProjectGateway,
    stop_words_gateway: FakeUserStopWordsGateway,
    price_filter_gateway: FakeUserPriceFilterGateway,
    notification_gateway: FakeProjectNotificationGateway,
    channel_notification_gateway: FakeChannelNotificationGateway,
    notifier: FakeTelegramNotifier,
    txn: FakeTransactionManager,
) -> ProjectNotificationService:
    return ProjectNotificationService(
        project_gateway=project_gateway,
        stop_words_gateway=stop_words_gateway,
        price_filter_gateway=price_filter_gateway,
        notification_gateway=notification_gateway,
        channel_notification_gateway=channel_notification_gateway,
        telegram_notifier=notifier,
        transaction_manager=txn,
        url_builder=MarketplaceUrlBuilder(
            [
                FLUrlStrategy(7),
                KworkUrlStrategy(8),
            ],
        ),
        channel_id=-100,
    )
