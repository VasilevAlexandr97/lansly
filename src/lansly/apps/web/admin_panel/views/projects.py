from sqlalchemy.orm.attributes import instance_state
from starlette_admin import ComputedField
from starlette_admin.contrib.sqla import ModelView

from lansly.projects.models import Customer, Project, ProjectProposal


class CustomerUsernameField(ComputedField):
    async def parse_obj(self, request, obj):  # noqa: ARG002
        customer = instance_state(obj).dict.get("customer")
        if customer is not None:
            return f"{customer.username}"
        return None



class ProjectView(ModelView):
    fields = [  # noqa: RUF012
        Project.id,
        Project.title,
        Project.description,
        Project.price,
        Project.possible_price_limit,
        Project.customer,
        CustomerUsernameField("username"),
        Project.offers,
        Project.created_at,
    ]
    fields_default_sort = [(Project.created_at, True)]  # noqa: RUF012


class CustomerView(ModelView):
    fields = [  # noqa: RUF012
        Customer.id,
        Customer.external_id,
        Customer.source,
        Customer.username,
        Customer.user_projects_count,
        Customer.user_hired_percent,
        Customer.profile_picture,
        Customer.created_at,
        Customer.updated_at,
    ]
    fields_default_sort = [(Customer.created_at, True)]  # noqa: RUF012


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
    fields_default_sort = [(ProjectProposal.created_at, True)]  # noqa: RUF012
