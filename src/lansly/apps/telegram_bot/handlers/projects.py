from aiogram import F, Router, types
from aiogram.enums import ChatType
from dishka.integrations.aiogram import FromDishka, inject

from lansly.apps.telegram_bot.keyboards import (
    GenerateProposalCB,
    build_profile_menu_kbd,
)
from lansly.apps.telegram_bot.messages import (
    already_generating_proposal_message,
    generating_proposal_message,
    generation_limit_exceeded_message,
    profile_not_set_message,
)
from lansly.preferences.exceptions import UserFreelancerProfileNotFoundError
from lansly.projects.dto import ProjectProposalGenerationRequestStatus
from lansly.projects.exceptions import GenerationLimitExceededError
from lansly.projects.services import (
    ProjectProposalRequestService,
)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(
    F.message.chat.type == ChatType.PRIVATE,
)


@router.callback_query(GenerateProposalCB.filter())
@inject
async def generate_proposal_request(
    call: types.CallbackQuery,
    callback_data: GenerateProposalCB,
    service: FromDishka[ProjectProposalRequestService],
):
    try:
        result = await service.request_generation(callback_data.project_id)
        if result.status == ProjectProposalGenerationRequestStatus.CREATED:
            text = generating_proposal_message()
            await call.answer(text, show_alert=True)

        elif (
            result.status
            == ProjectProposalGenerationRequestStatus.ALREADY_PENDING
        ):
            text = already_generating_proposal_message()
            await call.answer(text, show_alert=True)

        elif (
            result.status
            == ProjectProposalGenerationRequestStatus.ALREADY_GENERATED
            and result.generated_text
        ):
            await call.message.answer(result.generated_text)
            await call.answer()
        else:
            await call.answer()
    except UserFreelancerProfileNotFoundError:
        text = profile_not_set_message()
        keyboard = build_profile_menu_kbd()
        await call.message.answer(text, reply_markup=keyboard)
        await call.answer()
    except GenerationLimitExceededError as exc:
        text = generation_limit_exceeded_message(
            limit=exc.limit,
            is_pro=exc.is_pro,
        )
        await call.answer(text, show_alert=True)
