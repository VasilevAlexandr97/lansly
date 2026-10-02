import pytest

from fakes.infra import FakeDistributedLockManager, FakeTransactionManager
from fakes.notifications import FakeProjectNotificationQueue
from fakes.projects import (
    FakeCustomerGateway,
    FakeProjectCategoryGateway,
    FakeProjectGateway,
)

from lansly.projects.services import ProjectSyncService


@pytest.fixture
def sync_service(
    *,
    category_gateway: FakeProjectCategoryGateway,
    project_gateway: FakeProjectGateway,
    customer_gateway: FakeCustomerGateway,
    txn: FakeTransactionManager,
    lock_manager: FakeDistributedLockManager,
    notification_queue: FakeProjectNotificationQueue,
) -> ProjectSyncService:
    return ProjectSyncService(
        integrations=[],
        category_gateway=category_gateway,
        project_gateway=project_gateway,
        customer_gateway=customer_gateway,
        transaction_manager=txn,
        lock_manager=lock_manager,
        notification_queue=notification_queue,
    )
