from enum import StrEnum

ALL_DIMENSION = "all"
UNCATEGORIZED = "none"

SOURCE_DIMENSION_PREFIX = "source:"
CATEGORY_DIMENSION_PREFIX = "cat:"
BUCKET_DIMENSION_PREFIX = "bucket:"

METRIC_NAME_MAX_LENGTH = 64
DIMENSION_MAX_LENGTH = 128


class DailyMetricName(StrEnum):
    PROJECTS_COUNT = "projects.count"
    PROJECTS_SUM_PRICE = "projects.sum_price"
    PROJECTS_MIN_PRICE = "projects.min_price"
    PROJECTS_MAX_PRICE = "projects.max_price"
    PROJECTS_BUCKET_LT_1K = "projects.bucket.lt_1k"
    PROJECTS_BUCKET_FROM_1K_TO_5K = "projects.bucket.1k_5k"
    PROJECTS_BUCKET_FROM_5K_TO_15K = "projects.bucket.5k_15k"
    PROJECTS_BUCKET_FROM_15K_TO_30K = "projects.bucket.15k_30k"
    PROJECTS_BUCKET_GT_30K = "projects.bucket.gt_30k"


def source_dimension(source: str) -> str:
    return f"{SOURCE_DIMENSION_PREFIX}{source}"


def category_dimension(source: str, external_id: str | None) -> str:
    return (
        f"{CATEGORY_DIMENSION_PREFIX}{source}:{external_id or UNCATEGORIZED}"
    )
