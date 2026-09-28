from dishka import AsyncContainer
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin import (
    Breakpoints,
    ChartWidget,
    ColumnWidget,
    GridWidget,
    StatWidget,
    route,
)
from starlette_admin.views import CustomView
from starlette_admin.widgets import render_widget

from lansly.analytics.dto import CategoryFollowCounts
from lansly.analytics.services import OverviewService
from lansly.projects.consts import Marketplace


def get_days(request: Request) -> int:
    days = {"7": 7, "30": 30, "90": 90}.get(
        request.query_params.get("days"),
        7,
    )
    return days


async def count_users(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_users()


async def count_new_users(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_new_users(days)


async def count_new_users_from_site(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_new_users(days, source="site")


async def count_notifications(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_notifications(days)


async def count_notification_recipients(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_notification_recipients(days)


async def counts_daily_notifications(request: Request) -> list[dict]:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        points = await service.get_notification_counts_by_day(days)
        return [{"name": "day", "data": [point.count for point in points]}]


async def get_category_follow_counts(request: Request) -> CategoryFollowCounts:
    cached = getattr(request.state, "category_follow_counts", None)
    if cached is not None:
        return cached

    container: AsyncContainer = request.state.dishka_container
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        counts = await service.get_active_category_follow_counts()

    request.state.category_follow_counts = counts
    return counts


async def count_users_with_one_category(request: Request) -> int:
    return (await get_category_follow_counts(request)).one_category


async def count_users_with_multiple_categories(request: Request) -> int:
    return (await get_category_follow_counts(request)).two_or_more_categories


async def count_active_subscription_users(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_active_subscription_users()


async def count_projects(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_projects(days)


async def count_kwork_projects(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_projects(
            days=days,
            source=Marketplace.KWORK,
        )


async def count_fl_projects(request: Request) -> int:
    container: AsyncContainer = request.state.dishka_container
    days = get_days(request)
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        return await service.count_projects(days=days, source=Marketplace.FL)


count_users_stat = StatWidget(
    title="Количество пользователей(всего)",
    value_callback=count_users,
    color="success",
)

count_new_users_stat = StatWidget(
    title="Количество новых пользователей(за дни)",
    value_callback=count_new_users,
    color="success",
)

count_new_users_from_site_stat = StatWidget(
    title="Новые пользователи с сайта",
    value_callback=count_new_users_from_site,
    color="success",
)

count_notifications_stat = StatWidget(
    title="Количество уведомлений о проектах",
    value_callback=count_notifications,
    color="success",
)

count_notification_recipients_stat = StatWidget(
    title="Получатели уведомлений о проектах",
    value_callback=count_notification_recipients,
    color="success",
)

one_category_stat = StatWidget(
    title="Мониторят 1 категорию",
    value_callback=count_users_with_one_category,
)

multiple_categories_stat = StatWidget(
    title="Мониторят 2+ категории",
    value_callback=count_users_with_multiple_categories,
)

active_subscription_users_stat = StatWidget(
    title="Пользователи с активной подпиской",
    value_callback=count_active_subscription_users,
    color="success",
)

count_projects_stat = StatWidget(
    title="Количество проектов",
    value_callback=count_projects,
    color="success",
)

count_kwork_projects_stat = StatWidget(
    title="Количество KWORK проектов",
    value_callback=count_kwork_projects,
    color="success",
)

count_fl_projects_stat = StatWidget(
    title="Количество FL проектов",
    value_callback=count_fl_projects,
    color="success",
)

stats_row = GridWidget(
    children=[
        count_users_stat,
        count_new_users_stat,
        count_new_users_from_site_stat,
        count_notifications_stat,
        count_notification_recipients_stat,
        one_category_stat,
        multiple_categories_stat,
        active_subscription_users_stat,
    ],
    breakpoints=Breakpoints(default=1, md=2, lg=3),
    gutter=3,
)

project_stats_row = GridWidget(
    children=[
        count_projects_stat,
        count_kwork_projects_stat,
        count_fl_projects_stat,
    ],
    breakpoints=Breakpoints(default=1, md=2, lg=3),
    gutter=3,
)


async def build_notification_chart(request: Request) -> ChartWidget:
    container: AsyncContainer = request.state.dishka_container
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        points = await service.get_notification_counts_by_day(
            get_days(request),
        )

    async def series(_: Request) -> list[dict]:
        return [
            {
                "name": "Уведомления",
                "data": [point.count for point in points],
            },
        ]

    return ChartWidget(
        title="Уведомления по дням",
        chart_type="line",
        series_callback=series,
        options={
            "xaxis": {
                "categories": [
                    point.day.strftime("%d.%m") for point in points
                ],
            },
        },
        height=300,
    )


async def build_new_users_chart(request: Request) -> ChartWidget:
    container: AsyncContainer = request.state.dishka_container
    async with container() as req_c:
        service = await req_c.get(OverviewService)
        points = await service.get_new_user_counts_by_day(get_days(request))

    async def series(_: Request) -> list[dict]:
        return [
            {
                "name": "Новые пользователи",
                "data": [point.count for point in points],
            },
        ]

    return ChartWidget(
        title="Новые пользователи по дням",
        chart_type="line",
        series_callback=series,
        options={
            "xaxis": {
                "categories": [
                    point.day.strftime("%d.%m") for point in points
                ],
            },
        },
        height=300,
    )


class OverviewView(CustomView):
    menu_label = "Обзор"
    icon = "fa fa-chart-line"
    widget = stats_row

    @route("")
    async def index(self, request: Request) -> Response:
        days = get_days(request)
        assert self.templates is not None
        # widget = await self._resolve_widget(request)
        # assert widget is not None
        widget = ColumnWidget(
            children=[
                stats_row,
                project_stats_row,
                await build_new_users_chart(request),
                await build_notification_chart(request),
            ],
        )
        return self.templates.TemplateResponse(
            request=request,
            name="overview/index.html",
            context={
                "title": self.title(request),
                "days": days,
                "widget_html": await render_widget(
                    widget,
                    request,
                    self.templates.env,
                ),
                "widget_additional_css": widget.additional_css_links(request),
                "widget_additional_js": widget.additional_js_links(request),
            },
        )
