import asyncio
import random

from lansly.projects.consts import Marketplace
from lansly.projects.dto import MarketplaceProject
from lansly.projects.interfaces import (
    MarketplaceClient,
    ProjectCollector,
    ProjectGateway,
)


class KworkProjectCollector(ProjectCollector):
    source = Marketplace.KWORK

    def __init__(self, client: MarketplaceClient):
        self._client = client

    async def collect(self) -> list[MarketplaceProject]:
        return await self._client.get_projects()


class FlRuProjectCollector(ProjectCollector):
    source = Marketplace.FL

    def __init__(
        self,
        client: MarketplaceClient,
        project_gateway: ProjectGateway,
    ):
        self._client = client
        self.project_gateway = project_gateway

    async def collect(self) -> list[MarketplaceProject]:
        discovered = await self._client.get_projects()
        discovered_ids = [p.id for p in discovered]
        missing_ids = await self.project_gateway.get_missing_external_ids(
            external_ids=discovered_ids,
            source=self.source,
        )
        result = []
        for project in discovered:
            if project.id not in missing_ids:
                continue
            full_project = await self._client.get_project(project.id)
            if full_project is not None:
                result.append(full_project)
            await asyncio.sleep(random.uniform(1, 5))
        return result
