from lansly.projects.consts import Marketplace
from lansly.projects.interfaces import MarketplaceUrlStrategy
from lansly.projects.models import Customer, Project


class FLUrlStrategy(MarketplaceUrlStrategy):
    source = Marketplace.FL

    def __init__(self, ref_id: int | None = None):
        self.ref_id = ref_id

    def _add_refferal_param(self, url: str) -> str:
        if self.ref_id is None:
            return url
        return f"{url}?ref={self.ref_id}"

    def build_project_url(self, project: Project) -> str:
        url = f"https://fl.ru/projects/{project.external_id}/"
        return self._add_refferal_param(url)

    def build_customer_url(self, customer: Customer) -> None:
        return None
