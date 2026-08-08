from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SitemapEntry:
    loc: str
    lastmod: datetime | None = None
    changefreq: str | None = None
    priority: float | None = None


class SitemapSection(Protocol):
    async def entries(self) -> list[SitemapEntry]:
        raise NotImplementedError
