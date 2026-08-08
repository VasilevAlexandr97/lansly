from datetime import datetime
from decimal import Decimal

from lansly.preferences.consts import (
    MAX_FREE_CATEGORIES,
    MAX_FREE_STOP_WORDS,
    MAX_LENGTH_FREELANCER_PROFILE,
    MAX_PRO_STOP_WORDS,
)
from lansly.preferences.models import UserPriceFilter
from lansly.projects.consts import MAX_FREE_GENERATIONS, MAX_PRO_GENERATIONS
from lansly.projects.models import Project, ProjectCategory
from lansly.subscriptions.dto import SubscriptionInfoDTO
from lansly.subscriptions.models import PlanSlug


def project_message(project: Project, ref_id: int | None = None) -> str:
    project_link = f"https://kwork.ru/projects/{project.external_id}"
    if ref_id is not None:
        project_link += f"?ref={ref_id}"
    hashtag = f"#{project.category.title.replace(' ', '').lower()}"
    return (
        "🔔 Новый проект\n\n"
        f"📂 {project.category.title}\n\n"
        f"📌 <a href='{project_link}'><b>{project.title}</b></a>\n\n"
        f"💰 Бюджет\n"
        f"• Желаемый: {project.price} ₽\n"
        f"• Допустимый: {project.possible_price_limit} ₽\n\n"
        f"📝 {project.description}\n\n"
        f"{hashtag}\n\n"
        f"🔗 <a href='{project_link}'>Ссылка на проект</a>"
    )


def start_message() -> str:
    return (
        "👋 Добро пожаловать в <b>Lansly</b>\n\n"
        "Мониторю проекты на бирже Kwork и присылаю новые мгновенно.\n\n"
        "⚡ Что я делаю:\n"
        "• Мониторинг новых проектов\n"
        "• Мгновенные уведомления\n"
        "• Генерация автоматических откликов\n\n"
        "📂 Настрой категории — и я начну мониторинг"
    )


def menu_message(follow_categories: list[ProjectCategory]) -> str:
    follow_categories_str = "\n".join(
        f"• {cat.title}" for cat in follow_categories
    )
    if not follow_categories:
        follow_categories_str = "• Нет отслеживаемых категорий"
    return (
        "🏠 <b>Главное меню Lansly</b>\n\n"
        "⚡ <b>Lansly</b> отслеживает новые проекты на бирже <b>Kwork</b> "
        "и присылает подходящие задания автоматически.\n\n"
        "<b>📂 Отслеживаемые категории:</b>\n"
        f"{follow_categories_str}\n\n"
        "⚙️ Используйте меню ниже для управления настройками"
    )


def select_followed_categories_message() -> str:
    return "📂 Выберите категории для мониторинга"


def categories_limit_exceeded_message(limit: int) -> str:
    return (
        f"🔒 Бесплатный тариф ограничен {limit} категориями. "
        "Перейдите на PRO для доступа ко всем категориям."
    )


def unfollow_all_categories_message() -> str:
    return (
        "🗑️ Отписка от всех категорий выполнена.\n\n"
        "Уведомления о новых проектах приходить не будут.\n"
        "Чтобы возобновить мониторинг — выберите категории в меню."
    )


def profile_not_set_message() -> str:
    return (
        "👤 <b>Профиль фрилансера</b>\n\n"
        "Профиль ещё не заполнен.\n\n"
        "ℹ️ Профиль используется для генерации "
        "персонализированных откликов на проекты.\n"
        "Чем подробнее вы опишете себя и свои навыки — "
        "тем качественнее будут отклики.\n\n"
        "Нажмите «✏️ Редактировать», чтобы заполнить профиль."
    )


def profile_info_message(about: str) -> str:
    return (
        "👤 <b>Профиль фрилансера</b>\n\n"
        f"{about}\n\n"
        "ℹ️ Этот профиль используется для генерации откликов.\n"
        "Вы можете отредактировать его в любой момент."
    )


def start_edit_profile_message() -> str:
    return (
        "<b>Отправьте одним сообщением информацию о себе:</b>\n\n"
        "• Кто вы и чем занимаетесь\n"
        "• Ваш стек технологий / навыки\n"
        "• Опыт работы\n"
        "• Ссылки на портфолио\n"
        "• Релевантные проекты и специализацию\n\n"
        "<b>Чем подробнее профиль — тем качественнее будут отклики.</b>\n\n"
        "<b>Пример:</b>\n\n"
        "Я frontend-разработчик с опытом 5+ лет.\n"
        "Работаю с HTML, CSS, JavaScript, TypeScript, React, Next.js.\n"
        "Разрабатываю лендинги, интернет-магазины и CRM-системы.\n\n"
        "Есть опыт интеграции API, Telegram-ботов и админ-панелей.\n\n"
        "Портфолио:\n"
        "https://example.com\n"
        "https://github.com/example\n\n"
        f"⚠️ Максимум — {MAX_LENGTH_FREELANCER_PROFILE} символов."
    )


def profile_length_error_message() -> str:
    return (
        "❌ Текст профиля слишком длинный.\n\n"
        f"Максимальная длина — {MAX_LENGTH_FREELANCER_PROFILE} символов.\n\n"
        "Сократите описание и попробуйте снова."
    )


def stop_words_menu_message(words: list[str], limit: int) -> str:
    stop_words_list = "\n".join(
        f"{i}. {word}" for i, word in enumerate(words, start=1)
    )
    return (
        "🛑 <b>Стоп-слова</b>\n\n"
        "Стоп-слова — это фильтр для уведомлений.\n\n"
        "Если в названии или описании нового проекта "
        "встретится такое слово — вы <b>не получите</b> "
        "уведомление об этом проекте.\n\n"
        f"📝 Ваши стоп-слова ({len(words)}/{limit})\n\n"
        f"{stop_words_list}"
    )


def start_add_stop_words_message() -> str:
    return (
        "✏️ <b>Добавление стоп-слов</b>\n\n"
        "Введите одно или несколько слов через запятую.\n\n"
        "Проекты, содержащие эти слова в названии или описании, "
        "не будут приходить вам в уведомления.\n\n"
        "<b>Пример:</b>\n"
        "работа, тест, копирайтинг, telegram\n\n"
        'Чтобы отменить — нажмите кнопку "✖️ Отмена"'
    )


def start_delete_stop_words_message(words: list[str]) -> str:
    stop_words_list = "\n".join(
        f"{i}. {word}" for i, word in enumerate(words, start=1)
    )
    return (
        "🗑 <b>Удаление стоп-слов</b>\n\n"
        "Введите одно или несколько слов через запятую, "
        "которые хотите удалить из стоп-листа.\n\n"
        "<b>Текущие стоп-слова:</b>\n"
        f"{stop_words_list}\n\n"
        "<b>Пример:</b>\n"
        "тест, копирайтинг\n\n"
        'Чтобы отменить — нажмите кнопку "✖️ Отмена"'
    )


def empty_stop_words_delete_message() -> str:
    return "У вас пока нет стоп-слов, поэтому удалять нечего."


def stop_words_limit_exceeded_message(limit: int) -> str:
    return f"❌ Достигнут лимит в {limit} стоп-слов."


def price_filter_menu_message(
    price_filter: UserPriceFilter | None = None,
) -> str:
    text = (
        "💰 <b>Фильтр цен</b>\n\n"
        "Фильтр цен позволяет убирать из уведомлений проекты "
        "с бюджетом вне указанного диапазона.\n\n"
    )
    if price_filter:
        text += (
            f"✅ Текущий фильтр: от {price_filter.min_price}₽ "
            f"до {price_filter.max_price}₽"
        )
    else:
        text += "❌ Фильтр не установлен — приходят проекты с любой ценой."
    return text


def start_set_price_filter_message() -> str:
    return (
        "✏️ <b>Установка фильтра цен</b>\n\n"
        "Введите диапазон в формате: min-max\n\n"
        "Например:\n"
        "• 1000-50000 — проекты от 1000₽ до 50000₽\n\n"
        'Чтобы отменить — нажмите кнопку "✖️ Отмена"'
    )


def price_filter_format_error_message() -> str:
    return (
        "❌ Неверный формат. Введите два числа через дефис: min-max\n\n"
        "Пример: 1000-50000\n\n"
    )


def generating_proposal_message() -> str:
    return "🔄 Генерирую"


def generating_proposal_failed_message() -> str:
    return "😔 Не удалось сгенерировать отклик"


def already_generating_proposal_message() -> str:
    return "⏳ Уже генерирую"


def generation_limit_exceeded_message(limit: int, is_pro: bool) -> str:
    if is_pro:
        return (
            "❌ Лимит генераций на этот период исчерпан.\n\n"
            f"По тарифу PRO доступно {limit} генераций. "
            "Новый лимит появится после продления подписки."
        )
    return (
        "❌ Бесплатный лимит генераций исчерпан.\n\n"
        f"Бесплатно можно сгенерировать только {limit} откликов. "
        f"Оформите PRO подписку — {MAX_PRO_GENERATIONS} генераций в месяц."
    )


def pro_subscription_info_message(
    plan_slug: PlanSlug,
    price: Decimal,
    monthly_price: Decimal,
    duration_days: int,
) -> str:
    text = (
        "👑 PRO подписка\n\n"
        "Открой полный доступ к возможностям бота:\n\n"
        f"📂 Все категории - подписывайся не на {MAX_FREE_CATEGORIES}, "
        "а на любое количество категорий и не пропускай ни одного "
        "нового проекта\n\n"
        "🔔 Мгновенные уведомления - узнавай о новых заказах "
        "в выбранных категориях первым, пока их не разобрали "
        "конкуренты\n\n"
        f"🤖 {MAX_PRO_GENERATIONS} генераций откликов в месяц - "
        f"вместо {MAX_FREE_GENERATIONS} бесплатных "
        f"получи {MAX_PRO_GENERATIONS} откликов в месяц, "
        "сгенерированных нейросетью, которые помогут выделиться среди фрилансеров\n\n"
        "⚡️ Экономия времени - не нужно придумывать текст отклика "
        "самому, ИИ сделает это за секунды\n\n"
        f"🚫 {MAX_PRO_STOP_WORDS} стоп-слов - вместо "
        f"{MAX_FREE_STOP_WORDS} бесплатных фильтруй заказы по "
        f"{MAX_PRO_STOP_WORDS} стоп-словам и отсекай неподходящие "
        "проекты\n\n"
    )
    if plan_slug == PlanSlug.PRO_INITIAL:
        text += (
            f"🎁 Попробуй PRO всего за {price:.0f}₽ на {duration_days} дня, "
            f"далее — {monthly_price:.0f}₽/мес. Отменить можно в любой момент."
        )
    else:
        text += (
            "💎 Оформи полную PRO подписку и "
            "получи безлимитный доступ ко всем функциям бота"
        )
    return text


def payment_message(
    payment_id: str,
    email: str,
    amount: Decimal,
    link: str,
) -> str:
    return (
        f"🛒 Платеж: <b>{payment_id}</b>\n\n"
        f"💰 Cумма: {amount:.0f}₽\n\n"
        f"✅ Используется email: {email}\n\n"
        f"💳 Перейди по ссылке для оплаты: {link}\n\n"
        "Либо жми оплатить 👇"
    )


def payment_email_message() -> str:
    return "✍️ Введи свой email (он нужен для чека):"


def payment_email_validation_error_message() -> str:
    return "❌ Такой email не подходит. Попробуй ещё раз:"


def subscription_exists_message():
    return "👑 У вас уже оформлена PRO подписка."


def not_active_subscription_message() -> str:
    return (
        "👑 Управление подпиской\n\n"
        "У вас нет активной PRO подписки.\n\n"
        "Возможно, срок действия истёк.\n"
        "Оформите подписку, чтобы продолжить пользоваться:\n\n"
        "• 📂 Любое количество категорий\n"
        "• 🔔 Мгновенные уведомления\n"
        f"• 🤖 {MAX_PRO_GENERATIONS} генераций откликов\n"
        "• ⚡️ Экономия времени"
    )


def subscription_info_message(info: SubscriptionInfoDTO):
    status = "✅ Активна"
    if info.is_cancelled:
        status = "⏳ Отменена"
    expires_at = info.expires_at.strftime("%d.%m.%Y")
    text = (
        "👑 Управление подпиской\n\n"
        f"Тариф: {info.plan_name}\n"
        f"Статус: {status}\n"
        f"Оплачен до: {expires_at}\n"
        f"Осталось дней: {info.days_left}\n\n"
    )

    if info.is_cancelled:
        text += "Подписка отменена. PRO-доступ сохранится до конца периода."
    return text


def subscription_cancelled_message(expires_at: datetime) -> str:
    return (
        "✅ Подписка отменена.\n\n"
        f"PRO-доступ сохранится до {expires_at.strftime('%d.%m.%Y')}.\n"
        "Никаких списаний больше не будет.\n\n"
        "Спасибо, что были с нами!"
    )


def subscription_already_cancelled_message() -> str:
    return "❌ Подписка уже была отменена ранее."


def antiflood_message() -> str:
    return "✋ Слишком частые запросы"


def try_again_later_message() -> str:
    return "⚠️ Попробуйте позже"


def about_project_message() -> str:
    # TODO: хардкод ссылок
    return (
        "ℹ️ <b>Lansly</b>\n\n"
        "📊 Отслеживаю новые проекты на Kwork и "
        "помогаю генерировать отклики через нейросеть.\n\n"
        "🔗 <b>Полезные ссылки:</b>\n\n"
        "🌐 Сайт — <a href='https://lansly.ru'>lansly.ru</a>\n\n"
        "🆘 Поддержка — @askanonagent\n\n"
        "📢 Канал с проектами — https://t.me/freelance_pr_feed\n\n"
        "💬 Остались вопросы? Пиши в саппорт!"
    )


def error_message() -> str:
    # TODO: хардкод админа
    return (
        "😔 Произошла непредвиденная ошибка.\n\n"
        "Попробуйте еще раз немного позже. "
        "Если ошибка повторяется, сообщите администратору "
        "@askanonagent"
    )


def error_callback_message() -> str:
    return "😔 Произошла непредвиденная ошибка."
