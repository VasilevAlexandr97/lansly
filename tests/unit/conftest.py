import pytest

from fakes.infra import FakeDistributedLockManager, FakeTransactionManager
from fakes.projects import (
    FakeCustomerGateway,
    FakeMarketPlaceClient,
    FakeProjectCategoryGateway,
    FakeProjectCollector,
    FakeProjectGateway,
)
from fakes.users import FakeUserGateway, FakeUserRoleGateway

from lansly.common.password_hasher_bcrypt import PasswordHasherBcrypt
from lansly.projects.consts import Marketplace


@pytest.fixture
def txn() -> FakeTransactionManager:
    return FakeTransactionManager()


@pytest.fixture
def lock_manager() -> FakeDistributedLockManager:
    return FakeDistributedLockManager()


@pytest.fixture
def hasher() -> PasswordHasherBcrypt:
    return PasswordHasherBcrypt()


@pytest.fixture
def marketplace_client() -> FakeMarketPlaceClient:
    return FakeMarketPlaceClient()


@pytest.fixture
def user_gateway() -> FakeUserGateway:
    return FakeUserGateway()


@pytest.fixture
def role_gateway() -> FakeUserRoleGateway:
    return FakeUserRoleGateway()


@pytest.fixture
def category_gateway() -> FakeProjectCategoryGateway:
    return FakeProjectCategoryGateway()


@pytest.fixture
def project_gateway() -> FakeProjectGateway:
    return FakeProjectGateway()


@pytest.fixture
def customer_gateway() -> FakeCustomerGateway:
    return FakeCustomerGateway()


@pytest.fixture
def project_collector() -> FakeProjectCollector:
    return FakeProjectCollector()
