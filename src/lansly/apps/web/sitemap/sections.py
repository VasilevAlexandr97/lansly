from lansly.apps.web.sitemap.schema import SitemapEntry, SitemapSection
from lansly.articles.interfaces import ArticleGateway

HOME_ENTRY = SitemapEntry(
    loc="https://lansly.ru/",
    priority=1.0,
)


class StaticSitemapSection(SitemapSection):
    async def entries(self) -> list[SitemapEntry]:
        return [HOME_ENTRY]


class ArticlesSitemapSection(SitemapSection):
    def __init__(self, gateway: ArticleGateway):
        self.gateway = gateway

    async def entries(self) -> list[SitemapEntry]:
        articles = await self.gateway.get_published_all()
        list_entry = SitemapEntry(
            loc="https://lansly.ru/articles/",
            changefreq="weekly",
            priority=0.8,
        )
        return [
            list_entry,
            *[
                SitemapEntry(
                    loc=f"https://lansly.ru/articles/{article.slug}/",
                    lastmod=article.updated_at,
                    changefreq="monthly",
                    priority=0.6,
                )
                for article in articles
            ],
        ]
