from uuid import uuid7

import pytest

from fakes.infra import FakeTransactionManager
from fakes.users import FakeUserGateway, FakeUserRoleGateway

from lansly.common.password_hasher_bcrypt import PasswordHasherBcrypt
from lansly.users.exceptions import CreateUserError, UserAlreadyExistsError
from lansly.users.models import Role, User
from lansly.users.service import CreateAdminUserService


@pytest.fixture
def service(
    user_gateway: FakeUserGateway,
    role_gateway: FakeUserRoleGateway,
    txn: FakeTransactionManager,
    hasher: PasswordHasherBcrypt,
) -> CreateAdminUserService:
    return CreateAdminUserService(
        user_gateway=user_gateway,
        user_role_gateway=role_gateway,
        transaction_manager=txn,
        password_hasher=hasher,
    )


@pytest.mark.asyncio
async def test_create_creates_user_with_admin_role(
    service: CreateAdminUserService,
    user_gateway: FakeUserGateway,
    role_gateway: FakeUserRoleGateway,
    txn: FakeTransactionManager,
):
    dto = await service.create(
        username="admin",
        password="password",
    )
    assert dto.username == "admin"
    assert dto.user_id is not None

    assert len(user_gateway.added_users) == 1
    created = user_gateway.added_users[0]
    assert created.id == dto.user_id
    assert created.username == "admin"
    assert created.telegram_id is None
    assert created in user_gateway.users

    assert len(role_gateway.added_roles) == 1
    role = role_gateway.added_roles[0]
    assert role.name == Role.ADMIN
    assert role.user_id == created.id

    assert txn.commits == 1
    assert txn.rollbacks == 0


@pytest.mark.asyncio
async def test_create_hashes_password_not_plaintext(
    service: CreateAdminUserService,
    user_gateway: FakeUserGateway,
    hasher: PasswordHasherBcrypt,
):
    await service.create(username="admin", password="secret123")
    created = user_gateway.added_users[0]

    assert created.password_hash != "secret123"
    assert created.password_hash is not None
    assert hasher.verify("secret123", created.password_hash)
    assert not hasher.verify("wrong-password", created.password_hash)


@pytest.mark.asyncio
async def test_create_raises_when_username_exists(
    service: CreateAdminUserService,
    user_gateway: FakeUserGateway,
    txn: FakeTransactionManager,
):
    user_gateway.users.append(
        User(id=uuid7(), username="admin", password_hash="secret123"),
    )
    with pytest.raises(UserAlreadyExistsError):
        await service.create(username="admin", password="secret123")
    assert txn.commits == 0
    assert txn.rollbacks == 0


@pytest.mark.asyncio
async def test_create_rolls_back_on_duplicate_race(
    service: CreateAdminUserService,
    user_gateway: FakeUserGateway,
    txn: FakeTransactionManager,
):
    user_gateway.force_usernames = {"admin"}
    with pytest.raises(UserAlreadyExistsError):
        await service.create(username="admin", password="secret123")
    assert txn.rollbacks == 1
    assert txn.commits == 0


@pytest.mark.asyncio
async def test_create_rolls_back_on_create_error(
    service: CreateAdminUserService,
    user_gateway: FakeUserGateway,
    txn: FakeTransactionManager,
):
    user_gateway.create_error_usernames = {"admin"}
    with pytest.raises(CreateUserError):
        await service.create(username="admin", password="secret123")
    assert txn.rollbacks == 1
    assert txn.commits == 0
