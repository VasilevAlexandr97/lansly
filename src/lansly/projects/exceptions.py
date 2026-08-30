class ProjectCategoryNotFoundError(Exception):
    pass


class ParentCategoryExpectedError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class ProjectProposalNotFoundError(Exception):
    pass


class ProjectProposalGenerationError(Exception):
    pass


class GenerationLimitExceededError(Exception):
    def __init__(self, limit: int, is_pro: bool):
        self.limit = limit
        self.is_pro = is_pro
        super().__init__(
            f"Generation limit exceeded: {limit}, is_pro: {is_pro}",
        )


class MarketplaceIntegrationNotFoundError(Exception):
    pass
