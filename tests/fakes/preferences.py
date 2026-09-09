from lansly.preferences.dto import SourceCategoryFollowCountDTO
from lansly.projects.consts import Marketplace


# TODO: подумать добавить или нет интерфейс для основного сервиса
class FakeFollowService:
    def __init__(
        self,
        follow_counts: list[SourceCategoryFollowCountDTO] | None = None,
    ):
        self.follow_counts = (
            follow_counts
            if follow_counts is not None
            else [
                SourceCategoryFollowCountDTO(source=source, followed_count=0)
                for source in Marketplace
            ]
        )
        self.follow_counts_calls = 0

    async def get_followed_category_counts_by_source(
        self,
    ) -> list[SourceCategoryFollowCountDTO]:
        self.follow_counts_calls += 1
        return self.follow_counts
