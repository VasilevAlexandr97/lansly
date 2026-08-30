import asyncio
import base64
import logging
import random
import re

import httpx
import orjson

from selectolax.parser import HTMLParser, Node

from lansly.projects.consts import Marketplace
from lansly.projects.dto import MarketplaceCategory, MarketplaceProject
from lansly.projects.interfaces import MarketplaceClient

logger = logging.getLogger(__name__)


class FlRuClient(MarketplaceClient):
    _BASE_URL = "https://www.fl.ru"
    _PAGE_SLUG_RE = re.compile(r"page-\d+$")
    _NO_BUDGET_PHRASES = (
        "по договоренности",
        "по договорённости",
        "по результатам собеседования",
        "по итогам собеседования",
    )

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=self._BASE_URL,
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

    async def get_categories(self) -> list[MarketplaceCategory]:
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

    async def get_projects(self, page: int = 1) -> list[MarketplaceProject]:
        path = (
            "/projects/?kind=1"
            if page == 1
            else f"/projects/page-{page}/?kind=1"
        )
        tree = await self._fetch(path)
        projects = []
        for node in tree.css("div[id^=project-item]"):
            project = self._parse_project_item(node)
            if project is not None:
                projects.append(project)
        logger.info("Parsed projects: %s (page %s)", len(projects), page)
        return projects

    async def get_project(self, project_id: str) -> MarketplaceProject | None:
        tree = await self._fetch(f"/projects/{project_id}/")
        return await self._parse_project(tree, project_id)

    async def _fetch(self, path: str) -> HTMLParser:
        resp = await self._client.get(path)
        resp.raise_for_status()
        return HTMLParser(resp.text)

    def _parse_category_links(
        self,
        tree: HTMLParser,
        min_depth: int,
        parent_slug: str | None = None,
    ) -> list[MarketplaceCategory]:
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
            if self._PAGE_SLUG_RE.fullmatch(slug):
                continue

            if parent_slug is not None and parts[-2] != parent_slug:
                continue

            if slug in seen:
                continue
            seen.add(slug)
            result.append(
                MarketplaceCategory(
                    id=slug,
                    source=Marketplace.FLRU,
                    title=name,
                ),
            )
        return result

    def _normalise(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _parse_budget(self, text: str | None) -> tuple[int, bool]:
        if text is None:
            return 0, False
        normalised = self._normalise(text)
        if not normalised or normalised in self._NO_BUDGET_PHRASES:
            return 0, False
        digits = re.sub(r"\D", "", normalised)
        if not digits:
            return 0, False
        return int(digits), True

    def _decode_jwt_payload(self, token: str) -> dict:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        parts = raw.split(b".")
        if len(parts) < 2:
            return {}
        segment = parts[1]
        padding = b"=" * ((4 - len(segment) % 4) % 4)
        return orjson.loads(
            base64.urlsafe_b64decode(segment + padding).decode("utf-8"),
        )

    async def _fetch_offers_count(self, project_id: str) -> int:
        try:
            resp = await self._client.get(
                f"/projects/{project_id}/offers/range/",
            )
            resp.raise_for_status()
            payload = self._decode_jwt_payload(resp.json()["result"])
            return int(payload.get("freelancersCount", 0))
        except (
            httpx.HTTPError,
            KeyError,
            ValueError,
            TypeError,
            orjson.JSONDecodeError,
        ):
            logger.warning(
                "Failed to fetch offers count for project %s",
                project_id,
            )
            return 0

    def _parse_project_item(self, node: Node) -> MarketplaceProject | None:
        node_id = node.attributes.get("id")
        pr_id = (
            node_id.removeprefix("project-item")
            if node_id is not None
            else None
        )
        h2 = node.css_first("h2")
        title = h2.text(strip=True) if h2 is not None else None
        if pr_id is None or title is None:
            return None

        desc = node.css_first(".b-post__body")
        description = desc.text(strip=True) if desc is not None else ""

        price_node = node.css_first(".b-post__price")
        price_text = (
            price_node.text(strip=True) if price_node is not None else None
        )
        price, has_exact_budget = self._parse_budget(price_text)

        offers = 0
        offers_node = node.css_first("span[data-id='fl-view-count-href']")
        if offers_node is not None:
            try:
                offers = int(offers_node.text(strip=True).split(" ")[0])
            except (ValueError, KeyError, IndexError):
                offers = 0

        return MarketplaceProject(
            id=pr_id,
            category_id=None,
            source=Marketplace.FLRU,
            price=price,
            possible_price_limit=price,
            has_exact_budget=has_exact_budget,
            title=title,
            description=description,
            offers=offers,
            customer=None,
        )

    async def _parse_project(
        self,
        tree: HTMLParser,
        project_id: str,
    ) -> MarketplaceProject | None:
        title_node = tree.css_first(f"h1[id='prj_name_{project_id}']")
        if title_node is None:
            logger.warning("Project %s has not title", project_id)
            return None
        title = title_node.text(strip=True)

        description_node = tree.css_first(f"div[id='projectp{project_id}']")
        if description_node is None:
            logger.warning("Project %s has not description", project_id)
            return None
        description = description_node.text(strip=True)

        budget = 0
        has_exact_budget = False
        budget_node = next(
            (
                node
                for node in tree.css("div.text-4")
                if self._normalise(node.text(strip=True)).startswith("бюджет:")
            ),
            None,
        )
        if budget_node is not None:
            span = budget_node.css_first("span")
            if span is not None:
                budget, has_exact_budget = self._parse_budget(
                    span.text(strip=True),
                )
        else:
            logger.info("Project %s has no budget", project_id)

        offers = await self._fetch_offers_count(project_id)

        return MarketplaceProject(
            id=project_id,
            category_id=self._parse_category_id(tree),
            source=Marketplace.FLRU,
            price=budget,
            possible_price_limit=budget,
            has_exact_budget=has_exact_budget,
            title=title,
            description=description,
            offers=offers,
            customer=None,
        )

    def _parse_category_id(self, tree: HTMLParser) -> str | None:
        breadcrumbs = tree.css("div[itemprop='itemListElement']")
        if not breadcrumbs:
            return None
        item_link = breadcrumbs[-1].css_first("a[itemprop='item']")
        if item_link is None:
            return None
        href = item_link.attributes.get("href")
        if href is None:
            return None
        return href.strip("/").split("/")[-1]
