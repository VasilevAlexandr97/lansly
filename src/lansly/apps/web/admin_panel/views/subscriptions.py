from starlette_admin.contrib.sqla import ModelView

from lansly.subscriptions.models import SubscriptionPlan


class SubscriptionPlanView(ModelView):
    fields = [  # noqa: RUF012
        SubscriptionPlan.id,
        SubscriptionPlan.name,
        SubscriptionPlan.slug,
        SubscriptionPlan.price_rub,
        SubscriptionPlan.duration_days,
        SubscriptionPlan.is_active,
        SubscriptionPlan.created_at,
        SubscriptionPlan.updated_at,
    ]
