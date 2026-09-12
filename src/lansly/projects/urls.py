from collections.abc import Iterable

from lansly.projects.consts import Marketplace
from lansly.projects.dto import ProjectLinks
from lansly.projects.interfaces import MarketplaceUrlStrategy
from lansly.projects.models import Project


class MarketplaceUrlBuilder:
    def __init__(self, strategies: Iterable[MarketplaceUrlStrategy]):
        self._strategies = self._strategy_map(strategies)

    def _strategy_map(
        self,
        strategies: Iterable[MarketplaceUrlStrategy],
    ) -> dict[Marketplace, MarketplaceUrlStrategy]:
        result = {}
        for strategy in strategies:
            if strategy.source in result:
                raise ValueError(f"Duplicate URL strategy: {strategy.source}")
            result[strategy.source] = strategy
        return result

    def _get_strategy(self, source: str) -> MarketplaceUrlStrategy:
        try:
            return self._strategies[Marketplace(source)]
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"URL strategy is not configured: {source}",
            ) from exc

    def build_links(self, project: Project) -> ProjectLinks:
        strategy = self._get_strategy(project.source)
        return ProjectLinks(
            project_url=strategy.build_project_url(project),
            customer_url=(
                strategy.build_customer_url(project.customer)
                if project.customer is not None
                else None
            ),
        )
