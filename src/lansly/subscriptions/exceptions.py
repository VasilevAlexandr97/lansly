class SubscriptionPlanNotFoundError(Exception):
    pass


class SubscriptionAlreadyCancelledError(Exception):
    pass


class ActiveSubscriptionExistsError(Exception):
    pass


class ServiceTemporarilyUnavailableError(Exception):
    pass


class PaymentEmailNotFoundError(Exception):
    pass


class PaymentEmailRequiredError(Exception):
    pass


class PaymentEmailValidationError(Exception):
    pass


class PaymentMethodNotFoundError(Exception):
    pass


class PaymentAlreadyPaidError(Exception):
    pass
