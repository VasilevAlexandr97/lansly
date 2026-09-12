from dataclasses import dataclass

from lansly.projects.consts import Marketplace
from lansly.projects.interfaces import ProjectCollector


@dataclass(frozen=True, slots=True)
class LockOptions:
    key: str
    timeout: float | None
    blocking: bool = False
    blocking_timeout: float | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceIntegration:
    collector: ProjectCollector
    lock: LockOptions | None = None

    @property
    def source(self) -> Marketplace:
        return self.collector.source
