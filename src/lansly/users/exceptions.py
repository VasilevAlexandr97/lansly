class CreateUserError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class UserNotFoundByUsernameError(Exception):
    pass


class UserRoleCreationError(Exception):
    pass


class UserRoleNotFoundError(Exception):
    pass


class InvalidUsernameError(Exception):
    pass


class InvalidPasswordError(Exception):
    pass


class UsernameLengthError(Exception):
    pass


class PasswordLengthError(Exception):
    pass


class SourceLengthError(Exception):
    pass
