from starlette_admin.contrib.sqla import ModelView

from lansly.projects.models import Project, ProjectProposal


class ProjectView(ModelView):
    fields = [  # noqa: RUF012
        Project.id,
        Project.title,
        Project.description,
        Project.price,
        Project.possible_price_limit,
        Project.offers,
        Project.created_at,
    ]
    fields_default_sort = [(Project.created_at, True)]


class ProjectProposalView(ModelView):
    fields = [  # noqa: RUF012
        ProjectProposal.user,
        ProjectProposal.project,
        ProjectProposal.generated_text,
        ProjectProposal.prompt_tokens,
        ProjectProposal.completion_tokens,
        ProjectProposal.total_tokens,
        ProjectProposal.cost,
        ProjectProposal.prompt,
        ProjectProposal.created_at,
    ]
    fields_default_sort = [(ProjectProposal.created_at, True)]