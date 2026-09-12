import pytest

from lansly.users.consts import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SOURCE_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)
from lansly.users.exceptions import (
    InvalidPasswordError,
    InvalidUsernameError,
    PasswordLengthError,
    SourceLengthError,
    UsernameLengthError,
)
from lansly.users.validators import (
    password_validator,
    source_validator,
    username_validator,
)


def test_username_empty_raises_invalid_username():
    # Проверяет, что пустое имя пользователя вызывает InvalidUsernameError.
    with pytest.raises(InvalidUsernameError):
        username_validator("")


def test_username_too_short_raises_length_error():
    # Проверяет, что имя короче минимальной длины вызывает UsernameLengthError.
    with pytest.raises(UsernameLengthError):
        username_validator("a" * (USERNAME_MIN_LENGTH - 1))


@pytest.mark.parametrize(
    "length",
    [USERNAME_MIN_LENGTH, USERNAME_MAX_LENGTH],
)
def test_username_valid_boundaries(length: int):
    # Проверяет допустимость имени пользователя на обеих границах разрешённой
    # длины.
    username_validator("a" * length)


def test_username_too_long_raises_length_error():
    # Проверяет, что имя длиннее максимальной длины вызывает
    # UsernameLengthError.
    with pytest.raises(UsernameLengthError):
        username_validator("a" * (USERNAME_MAX_LENGTH + 1))


def test_password_empty_raises_invalid_password():
    # Проверяет, что пустой пароль вызывает InvalidPasswordError.
    with pytest.raises(InvalidPasswordError):
        password_validator("")


def test_password_too_short_raises_length_error():
    # Проверяет, что пароль короче минимальной длины вызывает
    # PasswordLengthError.
    with pytest.raises(PasswordLengthError):
        password_validator("a" * (PASSWORD_MIN_LENGTH - 1))


@pytest.mark.parametrize(
    "length",
    [PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH],
)
def test_password_valid_boundaries(length: int):
    # Проверяет допустимость пароля на обеих границах разрешённой длины.
    password_validator("a" * length)


def test_password_too_long_raises_length_error():
    # Проверяет, что пароль длиннее максимальной длины вызывает
    # PasswordLengthError.
    with pytest.raises(PasswordLengthError):
        password_validator("a" * (PASSWORD_MAX_LENGTH + 1))


def test_source_none_is_valid():
    # Проверяет допустимость отсутствующего источника пользователя, переданного
    # как None.
    source_validator(None)


def test_source_empty_raises_length_error():
    # Проверяет, что пустая строка источника пользователя вызывает
    # SourceLengthError.
    with pytest.raises(SourceLengthError):
        source_validator("")


def test_source_valid_boundary():
    # Проверяет допустимость источника пользователя максимальной разрешённой
    # длины.
    source_validator("a" * SOURCE_MAX_LENGTH)


def test_source_too_long_raises_length_error():
    # Проверяет, что источник пользователя длиннее разрешённого вызывает
    # SourceLengthError.
    with pytest.raises(SourceLengthError):
        source_validator("a" * (SOURCE_MAX_LENGTH + 1))
