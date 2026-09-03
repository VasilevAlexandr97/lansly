from enum import StrEnum


class Marketplace(StrEnum):
    KWORK = "kwork"
    FLRU = "flru"


MARKETPLACE_LABELS = {Marketplace.KWORK: "Kwork", Marketplace.FLRU: "FL.ru"}


MAX_FREE_GENERATIONS = 3
MAX_PRO_GENERATIONS = 80
