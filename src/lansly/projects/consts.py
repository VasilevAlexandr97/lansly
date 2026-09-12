from enum import StrEnum


class Marketplace(StrEnum):
    KWORK = "kwork"
    FL = "fl"


MARKETPLACE_LABELS = {Marketplace.KWORK: "KWORK", Marketplace.FL: "FL"}


MAX_FREE_GENERATIONS = 3
MAX_PRO_GENERATIONS = 80
