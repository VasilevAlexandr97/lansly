from aiogram.fsm.state import State, StatesGroup


class OnboardingState(StatesGroup):
    select_marketplace = State()
    select_direction = State()
    select_category = State()


class CategorySettingsState(StatesGroup):
    select_marketplace = State()
    select_direction = State()
    select_category = State()
    confirm_disable_monitoring = State()


class FreelancerProfileState(StatesGroup):
    edit = State()


class StopWordsState(StatesGroup):
    add = State()
    delete = State()


class PriceFilterState(StatesGroup):
    set = State()


class PaymentState(StatesGroup):
    set_email = State()
