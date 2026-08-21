import asyncio
import logging
import random
import re

import httpx

from selectolax.parser import HTMLParser

from lansly.projects.consts import MarketPlace
from lansly.projects.dto import MarketPlaceCategory
from lansly.projects.interfaces import MarketPlaceClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.fl.ru"
_PAGE_SLUG_RE = re.compile(r"page-\d+$")


class FlRuClient(MarketPlaceClient):
    source = MarketPlace.FLRU

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )
        self._min_delay = 1.0
        self._max_delay = 5.0

    async def _fetch(self, path: str) -> HTMLParser:
        resp = await self._client.get(path)
        resp.raise_for_status()
        return HTMLParser(resp.text)

    def _parse_category_links(
        self,
        tree: HTMLParser,
        min_depth: int,
        parent_slug: str | None = None,
    ) -> list[MarketPlaceCategory]:
        links = tree.css('a[href*="/projects/category/"]')
        seen: set[str] = set()
        result = []

        for link in links:
            href = link.attributes.get("href", "")
            name = link.text(strip=True)
            if not href or not name:
                continue

            parts = href.strip("/").split("/")
            if len(parts) < min_depth:
                continue

            slug = parts[-1]
            if _PAGE_SLUG_RE.fullmatch(slug):
                continue

            if parent_slug is not None and parts[-2] != parent_slug:
                continue

            if slug in seen:
                continue
            seen.add(slug)
            result.append(
                MarketPlaceCategory(
                    id=slug,
                    source=MarketPlace.FLRU,
                    title=name,
                ),
            )
        return result

    async def get_categories(self) -> list[MarketPlaceCategory]:
        tree = await self._fetch("/projects/")
        categories = self._parse_category_links(tree, min_depth=3)
        for cat in categories:
            subcat_tree = await self._fetch(f"/projects/category/{cat.id}/")
            subcats = self._parse_category_links(
                subcat_tree,
                min_depth=4,
                parent_slug=cat.id,
            )
            cat.subcategories = tuple(subcats)
            delay = random.uniform(self._min_delay, self._max_delay)
            logger.debug(f"Sleep: {delay}s")
            await asyncio.sleep(delay)
        return categories

    async def get_projects(
        self,
        categories_ids: list[int | str],
        page: int = 1,
    ) -> list[MarketPlaceProject]:
        pass
