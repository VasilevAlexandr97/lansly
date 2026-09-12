import argparse
import asyncio
import logging

from aiogram import Bot

from lansly.main.config import Config, get_config
from lansly.main.di import (
    WorkerProvider,
    create_container,
)
from lansly.projects.services import ProjectCategoryService
from lansly.statistics.services import DailyMetricsService, WeeklyReportService
from lansly.users.service import CreateAdminUserService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lansly")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-categories")
    admin = sub.add_parser("create-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--password", required=True)
    sub.add_parser("recalc-daily-metrics")
    sub.add_parser("weekly-report")
    return parser


async def main():
    config = get_config()
    logging.basicConfig(
        level=logging.INFO if not config.debug else logging.DEBUG,
    )
    bot = Bot(token=config.telegram_bot.token)
    container = create_container(
        providers=[WorkerProvider()],
        context={Config: config, Bot: bot},
    )

    args = build_parser().parse_args()
    async with container() as c_req:
        if args.command == "import-categories":
            service = await c_req.get(ProjectCategoryService)
            await service.import_categories()
        elif args.command == "create-admin":
            service = await c_req.get(CreateAdminUserService)
            await service.create(args.username, args.password)
            logger.info("Admin user created")
        elif args.command == "recalc-daily-metrics":
            service = await c_req.get(DailyMetricsService)
            await service.recompute_all()
            logger.info("Recompute all daily metrics success")
        elif args.command == "weekly-report":
            service = await c_req.get(WeeklyReportService)
            report = await service.build()
            logger.info(report.to_json())
    await container.close()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
