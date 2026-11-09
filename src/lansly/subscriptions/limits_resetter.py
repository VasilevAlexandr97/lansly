from uuid import UUID

from lansly.projects.gateways import UserGenerationUsageGateway
from lansly.subscriptions.interfaces import SubscriptionLimitsResetter


class SubscriptionLimitsResetterImpl(SubscriptionLimitsResetter):
    def __init__(
        self,
        usage_gateway: UserGenerationUsageGateway,
    ):
        self.usage_gateway = usage_gateway

    async def reset_pro_generations(self, user_id: UUID) -> None:
        usage = await self.usage_gateway.get_or_create(user_id)
        usage.reset_pro_generations()
