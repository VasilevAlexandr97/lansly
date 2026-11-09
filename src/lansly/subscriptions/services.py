import logging

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid7

from redis import RedisError
from redis.asyncio import Redis
from redis.asyncio.lock import Lock
from redis.exceptions import LockError

from lansly.auth.interfaces import IdProvider
from lansly.common.interfaces.transaction_manager import TransactionManager
from lansly.infra.yookassa.client import (
    AmountData,
    ConfirmationRedirectData,
    ConfirmationType,
    Currency,
    CustomerData,
    PaymentRequest,
    ReceiptData,
    ReceiptItemData,
    Status,
    YooKassaClient,
)
from lansly.notifications.interfaces import (
    SubscriptionActivatedNotificationQueue,
    SubscriptionRenewalNotificationQueue,
)
from lansly.subscriptions.dto import PlanForUserDTO, SubscriptionInfoDTO
from lansly.subscriptions.exceptions import (
    ActiveSubscriptionExistsError,
    PaymentAlreadyPaidError,
    PaymentEmailNotFoundError,
    PaymentEmailRequiredError,
    PaymentMethodNotFoundError,
    ServiceTemporarilyUnavailableError,
    SubscriptionAlreadyCancelledError,
    SubscriptionPlanNotFoundError,
)
from lansly.subscriptions.gateways import (
    PaymentGateway,
    SubscriptionGateway,
    SubscriptionPlanGateway,
)
from lansly.subscriptions.interfaces import SubscriptionLimitsResetter
from lansly.subscriptions.models import (
    Payment,
    PaymentStatus,
    PlanSlug,
    Subscription,
    SubscriptionPlan,
)
from lansly.subscriptions.validators import payment_email_validator

logger = logging.getLogger(__name__)


class SubscriptionPaymentService:
    def __init__(
        self,
        subscription_plan_gateway: SubscriptionPlanGateway,
        subscription_gateway: SubscriptionGateway,
        payment_gateway: PaymentGateway,
        id_provider: IdProvider,
        payment_client: YooKassaClient,
        transaction_manager: TransactionManager,
        redis_client: Redis,
    ):
        self.subscription_plan_gateway = subscription_plan_gateway
        self.subscription_gateway = subscription_gateway
        self.payment_gateway = payment_gateway
        self.id_provider = id_provider
        self.payment_client = payment_client
        self.transaction_manager = transaction_manager
        self.redis_client = redis_client

    def _payment_lock(self, user_id: UUID):
        return Lock(
            self.redis_client,
            f"create_payment:{user_id}",
            timeout=120,
            blocking_timeout=30,
        )

    async def _get_initial_or_monthly_plan(
        self,
        user_id: UUID,
    ) -> SubscriptionPlan:
        previous_subscriptions = await self.subscription_gateway.get(user_id)
        if previous_subscriptions:
            plan = await self.subscription_plan_gateway.get_by_slug(
                PlanSlug.PRO_MONTHLY,
            )
        else:
            plan = await self.subscription_plan_gateway.get_by_slug(
                PlanSlug.PRO_INITIAL,
            )
        if not plan:
            raise SubscriptionPlanNotFoundError
        return plan

    async def get_plan_for_user(self) -> PlanForUserDTO:
        user_id = await self.id_provider.get_current_user_id()
        is_active = await self.subscription_gateway.has_active(user_id)
        if is_active:
            raise ActiveSubscriptionExistsError
        plan = await self._get_initial_or_monthly_plan(user_id)
        monthly_price = plan.price_rub
        if plan.slug == PlanSlug.PRO_INITIAL:
            pro_plan = await self.subscription_plan_gateway.get_by_slug(
                PlanSlug.PRO_MONTHLY,
            )
            if not pro_plan:
                raise SubscriptionPlanNotFoundError
            monthly_price = pro_plan.price_rub
        return PlanForUserDTO(
            slug=PlanSlug(plan.slug),
            price=plan.price_rub,
            monthly_price=monthly_price,
            duration_days=plan.duration_days,
        )

    async def get_or_create_pending_payment(
        self,
        email: str | None = None,
    ) -> Payment:
        user_id = await self.id_provider.get_current_user_id()
        lock = self._payment_lock(user_id)
        try:
            async with lock:
                is_active = await self.subscription_gateway.has_active(user_id)
                if is_active:
                    raise ActiveSubscriptionExistsError
                if email is None:
                    email = await self.payment_gateway.get_last_payment_email(
                        user_id,
                    )
                if not email:
                    raise PaymentEmailRequiredError
                payment_email_validator(email)
                existing = await self.payment_gateway.get_pending_payment(
                    user_id,
                )
                now = datetime.now(UTC)

                if existing:
                    yookassa_payment = await self.payment_client.get_payment(
                        existing.yookassa_payment_id,
                    )
                    if yookassa_payment.status == Status.PENDING:
                        return existing
                    if yookassa_payment.status == Status.SUCCEEDED:
                        raise PaymentAlreadyPaidError
                    if yookassa_payment.status == Status.CANCELED:
                        error = (
                            yookassa_payment.cancellation_details.reason
                            if yookassa_payment.cancellation_details
                            else None
                        )
                        existing.mark_canceled(error=error, dt=now)
                plan = await self._get_initial_or_monthly_plan(user_id)
                payment_request = PaymentRequest(
                    amount=AmountData(
                        value=str(plan.price_rub),
                        currency=Currency.RUB,
                    ),
                    description=plan.name,
                    receipt=ReceiptData(
                        customer=CustomerData(
                            email=email,
                        ),
                        items=[
                            ReceiptItemData(
                                description=plan.name,
                                amount=AmountData(
                                    value=str(plan.price_rub),
                                    currency=Currency.RUB,
                                ),
                                vat_code=1,
                                quantity=1,
                            ),
                        ],
                    ),
                    # TODO: урл захардкожен, возможно стоит вынести в конфиг
                    confirmation=ConfirmationRedirectData(
                        type=ConfirmationType.REDIRECT,
                        return_url="https://t.me/lansly_bot",
                    ),
                    metadata={
                        "plan_id": str(plan.id),
                    },
                    save_payment_method=True,
                    capture=True,
                )
                yookassa_payment = await self.payment_client.create_payment(
                    payment_request,
                )
                logger.debug(f"YOOKASSA_PAYMENT: {yookassa_payment}")
                new_payment = Payment(
                    id=uuid7(),
                    user_id=user_id,
                    yookassa_payment_id=yookassa_payment.id,
                    yookassa_payment_method_id=None,
                    amount=Decimal(yookassa_payment.amount.value),
                    status=PaymentStatus.PENDING,
                    email=email,
                    link=yookassa_payment.confirmation.confirmation_url,
                    paid_at=None,
                    created_at=now,
                    updated_at=now,
                )
                await self.payment_gateway.add(new_payment)
                await self.transaction_manager.commit()
                return new_payment
        except RedisError:
            raise ServiceTemporarilyUnavailableError


class PaymentVerificationService:
    def __init__(
        self,
        payment_gateway: PaymentGateway,
        payment_client: YooKassaClient,
        subscription_plan_gateway: SubscriptionPlanGateway,
        subscription_gateway: SubscriptionGateway,
        limit_resetter: SubscriptionLimitsResetter,
        transaction_manager: TransactionManager,
        notify_queue: SubscriptionActivatedNotificationQueue,
        redis_client: Redis,
    ):
        self.payment_gateway = payment_gateway
        self.payment_client = payment_client
        self.subscription_plan_gateway = subscription_plan_gateway
        self.subscription_gateway = subscription_gateway
        self.limit_resetter = limit_resetter
        self.transaction_manager = transaction_manager
        self.notify_queue = notify_queue
        self.redis_client = redis_client

    def _verification_lock(self) -> Lock:
        return Lock(
            self.redis_client,
            "payment_verification",
            timeout=60,
            blocking_timeout=0,
        )

    # TODO: слишком большой метод, подумать как правильно его разбить
    async def verify_pending_payments(self):
        try:
            lock = self._verification_lock()
            async with lock:
                unpaid_payments = (
                    await self.payment_gateway.get_recent_unpaid_payments()
                )
                logger.info(f"UNPAID_PAYMENTS: {unpaid_payments}")
                if not unpaid_payments:
                    return

                now = datetime.now(UTC)
                for payment in unpaid_payments:
                    try:
                        yookassa_payment = (
                            await self.payment_client.get_payment(
                                payment.yookassa_payment_id,
                            )
                        )
                        logger.info(f"YOOKASSA PAYMENT: {yookassa_payment}")
                        if yookassa_payment.status == Status.SUCCEEDED:
                            pm = yookassa_payment.payment_method
                            if not pm or not pm.id:
                                logger.error(
                                    f"SUCCEEDED payment {payment.id} "
                                    "has no payment_method — skipping",
                                )
                                continue
                            if not yookassa_payment.metadata:
                                logger.error(
                                    f"SUCCEEDED payment {payment.id} "
                                    f"(yookassa_id={payment.yookassa_payment_id}) "
                                    " has no metadata - cannot determine plan, skipping",
                                )
                                continue
                            plan_id = yookassa_payment.metadata.get(
                                "plan_id",
                            )
                            if not plan_id:
                                logger.error(
                                    f"SUCCEEDED payment {payment.id} "
                                    f"(yookassa_id={payment.yookassa_payment_id}) "
                                    f" has metadata without 'plan_id' "
                                    f"(metadata={yookassa_payment.metadata}) — skipping",
                                )
                                continue
                            plan = (
                                await self.subscription_plan_gateway.get_by_id(
                                    UUID(plan_id),
                                )
                            )
                            if not plan:
                                logger.error(
                                    f"Subscription plan id={plan_id} "
                                    f"(from payment {payment.id} metadata) "
                                    "not found in DB — skipping",
                                )
                                continue
                            payment.mark_succeeded(pm.id, dt=now)
                            expires_at = (
                                now + timedelta(days=plan.duration_days)
                            ).replace(
                                hour=23,
                                minute=59,
                                second=59,
                                microsecond=0,
                            )
                            subscription = Subscription(
                                id=uuid7(),
                                user_id=payment.user_id,
                                plan_id=plan.id,
                                payment_id=payment.id,
                                started_at=now,
                                expires_at=expires_at,
                                created_at=now,
                                updated_at=now,
                                renewal_attempts=0,
                            )
                            await self.subscription_gateway.add(
                                subscription,
                            )
                            await self.limit_resetter.reset_pro_generations(
                                payment.user_id,
                            )
                            await self.transaction_manager.commit()
                            await self.notify_queue.enqueue(
                                payment.user_id,
                            )
                            await lock.extend(60)
                        elif yookassa_payment.status == Status.CANCELED:
                            error = (
                                yookassa_payment.cancellation_details.reason
                                if yookassa_payment.cancellation_details
                                else None
                            )
                            payment.mark_canceled(error=error, dt=now)
                            await self.transaction_manager.commit()
                    except Exception:
                        logger.exception("VERIFY PAYMENT ERROR")
        except LockError:
            logger.info("Verification skipped — lock held by another worker")
        except RedisError:
            raise ServiceTemporarilyUnavailableError


class SubscriptionManagementService:
    def __init__(
        self,
        subscription_gateway: SubscriptionGateway,
        id_provider: IdProvider,
        transaction_manager: TransactionManager,
    ):
        self.subscription_gateway = subscription_gateway
        self.id_provider = id_provider
        self.transaction_manager = transaction_manager

    async def get_active_subscription_info(self) -> SubscriptionInfoDTO | None:
        user_id = await self.id_provider.get_current_user_id()
        subscription = await self.subscription_gateway.get_latest_active(
            user_id,
            with_plan=True,
        )
        if not subscription:
            return None
        is_cancelled = False
        if subscription.cancelled_at:
            is_cancelled = True
        days_left = (subscription.expires_at - datetime.now(UTC)).days
        return SubscriptionInfoDTO(
            plan_name=subscription.plan.name,
            plan_slug=PlanSlug(subscription.plan.slug),
            is_cancelled=is_cancelled,
            started_at=subscription.started_at,
            expires_at=subscription.expires_at,
            days_left=days_left,
        )

    async def cancel_subscription(self) -> Subscription:
        user_id = await self.id_provider.get_current_user_id()
        subscription = await self.subscription_gateway.get_latest_active(
            user_id,
        )
        if not subscription or subscription.cancelled_at is not None:
            raise SubscriptionAlreadyCancelledError
        subscription.cancelled()
        await self.transaction_manager.commit()
        return subscription


class SubscriptionRenewalService:
    def __init__(
        self,
        subscription_plan_gateway: SubscriptionPlanGateway,
        subscription_gateway: SubscriptionGateway,
        payment_gateway: PaymentGateway,
        payment_client: YooKassaClient,
        limits_resetter: SubscriptionLimitsResetter,
        transaction_manager: TransactionManager,
        notify_queue: SubscriptionRenewalNotificationQueue,
        redis_client: Redis,
    ):
        self.subscription_plan_gateway = subscription_plan_gateway
        self.subscription_gateway = subscription_gateway
        self.payment_gateway = payment_gateway
        self.payment_client = payment_client
        self.limits_resetter = limits_resetter
        self.transaction_manager = transaction_manager
        self.notify_queue = notify_queue
        self.redis_client = redis_client

    def _renewal_subscription_lock(self) -> Lock:
        return Lock(
            self.redis_client,
            "renewal_subscription_lock",
            timeout=60,
            blocking_timeout=0,
        )

    async def _attemp_renewal(self, subscription: Subscription):
        plan = await self.subscription_plan_gateway.get_by_slug(
            slug=PlanSlug.PRO_MONTHLY,
        )
        if not plan:
            raise SubscriptionPlanNotFoundError
        payment_method = await self.payment_gateway.get_last_payment_method(
            subscription.user_id,
        )
        if not payment_method:
            raise PaymentMethodNotFoundError
        email = await self.payment_gateway.get_last_payment_email(
            subscription.user_id,
        )
        if not email:
            raise PaymentEmailNotFoundError

        payment_request = PaymentRequest(
            amount=AmountData(
                value=f"{plan.price_rub}",
                currency="RUB",
            ),
            description=f"Продление {plan.name}",
            payment_method_id=payment_method,
            capture=True,
        )
        result = await self.payment_client.create_payment(
            payment_request=payment_request,
        )
        logger.debug(f"SUBSCRIPTION RENEWAL: {result}")
        now = datetime.now(UTC)
        if result.status == Status.SUCCEEDED:
            subscription.finish()
            new_payment = Payment(
                id=uuid7(),
                user_id=subscription.user_id,
                yookassa_payment_id=result.id,
                yookassa_payment_method_id=result.payment_method.id,
                amount=plan.price_rub,
                status=PaymentStatus.SUCCEEDED,
                email=email,
                link="",
                paid_at=now,
                created_at=now,
                updated_at=now,
            )
            expires_at = (now + timedelta(days=plan.duration_days)).replace(
                hour=23,
                minute=59,
                second=59,
                microsecond=0,
            )
            new_subscription = Subscription(
                id=uuid7(),
                user_id=subscription.user_id,
                plan_id=plan.id,
                payment_id=new_payment.id,
                started_at=now,
                expires_at=expires_at,
                cancelled_at=None,
                created_at=now,
                updated_at=now,
                renewal_attempts=0,
            )
            await self.payment_gateway.add(new_payment)
            await self.subscription_gateway.add(new_subscription)
            await self.limits_resetter.reset_pro_generations(
                subscription.user_id,
            )
            await self.transaction_manager.commit()
            await self.notify_queue.enqueue_renewed(
                user_id=new_subscription.user_id,
                new_expires_at=new_subscription.expires_at,
            )
        elif result.status == Status.CANCELED:
            error = (
                result.cancellation_details.reason
                if result.cancellation_details
                else None
            )
            pm_id = result.payment_method.id if result.payment_method else None
            new_payment = Payment(
                id=uuid7(),
                user_id=subscription.user_id,
                yookassa_payment_id=result.id,
                yookassa_payment_method_id=pm_id,
                amount=plan.price_rub,
                status=PaymentStatus.FAILED,
                email=email,
                link="",
                paid_at=now,
                error=error,
                created_at=now,
                updated_at=now,
            )
            await self.payment_gateway.add(new_payment)
            subscription.renewal_attempts += 1
            if subscription.renewal_attempts >= 3:
                subscription.finish()
                await self.transaction_manager.commit()
                await self.notify_queue.enqueue_revoked(subscription.user_id)
            else:
                subscription.expires_at = now + timedelta(hours=8)
                await self.transaction_manager.commit()
                await self.notify_queue.enqueue_retry(subscription.user_id)

    async def renew_subscriptions(self):
        lock = self._renewal_subscription_lock()
        async with lock:
            due = await self.subscription_gateway.find_due_for_renewal()
            logger.info(f"DUE FOR RENEWAL SUBSCRIPTIONS: {due}")
            for sub in due:
                try:
                    await self._attemp_renewal(sub)
                except:
                    logger.exception("ATTEMP RENEWAL SKIPPED")
