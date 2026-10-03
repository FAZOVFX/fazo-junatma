"""Manual payment review. No gateway calls and no automatic approval."""

from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import (
    MAX_PENDING_PAYMENTS,
    MAX_TOPUP_UZS,
    MIN_TOPUP_UZS,
    PAYMENT_APPROVED,
    PAYMENT_METHOD_MANUAL,
    PAYMENT_PENDING,
    PAYMENT_PREMIUM,
    PAYMENT_REJECTED,
    PAYMENT_WALLET,
    PREMIUM_PRICE_UZS,
    WALLET_TOPUP,
)
from backend.database.models import Payment, User, WalletTransaction
from backend.services.errors import AppError
from backend.services.locks import resource_lock
from backend.services.subscription_service import apply_premium
from backend.utils.formatting import format_uzs, utcnow


class PaymentService(ABC):
    @abstractmethod
    async def create_payment(self, session, user, payment_type: str, amount_uzs: int | None, description: str | None, metadata: dict | None, now=None):
        raise NotImplementedError

    @abstractmethod
    async def approve_payment(self, session, payment_id: int, admin_telegram_id: int, now=None):
        raise NotImplementedError

    @abstractmethod
    async def reject_payment(self, session, payment_id: int, admin_telegram_id: int, now=None):
        raise NotImplementedError

    @abstractmethod
    async def get_pending_payments(self, session, limit: int = 50):
        raise NotImplementedError


class ManualPaymentService(PaymentService):
    async def create_payment(
        self,
        session: AsyncSession,
        user: User,
        payment_type: str,
        amount_uzs: int | None,
        description: str | None,
        metadata: dict | None = None,
        now=None,
    ) -> Payment:
        now = now or utcnow()
        if payment_type == PAYMENT_PREMIUM:
            amount = PREMIUM_PRICE_UZS
            description = description or "Premium 30 kun"
        elif payment_type == PAYMENT_WALLET:
            if amount_uzs is None or not isinstance(amount_uzs, int):
                raise AppError(422, "Summani kiriting.")
            if amount_uzs < MIN_TOPUP_UZS or amount_uzs > MAX_TOPUP_UZS:
                raise AppError(
                    422,
                    f"Summa {format_uzs(MIN_TOPUP_UZS)} dan {format_uzs(MAX_TOPUP_UZS)} gacha bo‘lishi kerak.",
                )
            amount = amount_uzs
            description = description or "Balans to‘ldirish"
        else:
            raise AppError(422, "To‘lov turi noto‘g‘ri.")

        pending_count = int(
            await session.scalar(
                select(func.count(Payment.id)).where(
                    Payment.user_id == user.id,
                    Payment.status == PAYMENT_PENDING,
                )
            )
            or 0
        )
        if pending_count >= MAX_PENDING_PAYMENTS:
            raise AppError(429, "Juda ko‘p kutilayotgan to‘lov bor. Admin javobini kuting.")

        payment = Payment(
            user_id=user.id,
            type=payment_type,
            amount_uzs=amount,
            method=PAYMENT_METHOD_MANUAL,
            status=PAYMENT_PENDING,
            screenshot_file_id=None,
            description=description[:500],
            created_at=now,
            reviewed_at=None,
            reviewed_by=None,
            payment_metadata=metadata or {},
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment

    async def attach_screenshot(
        self,
        session: AsyncSession,
        user: User,
        screenshot_file_id: str,
        payment_id: int | None = None,
        now=None,
    ) -> tuple[Payment | None, bool]:
        now = now or utcnow()
        if payment_id is not None:
            payment = await session.get(Payment, payment_id)
            if payment is None or payment.user_id != user.id:
                raise AppError(404, "To‘lov topilmadi.")
        else:
            payment = await session.scalar(
                select(Payment)
                .where(
                    Payment.user_id == user.id,
                    Payment.status == PAYMENT_PENDING,
                    Payment.screenshot_file_id.is_(None),
                )
                .order_by(Payment.created_at.desc())
            )
        if payment is None:
            return None, False
        if payment.status != PAYMENT_PENDING:
            raise AppError(409, "Bu to‘lov allaqachon ko‘rib chiqilgan.")
        if payment.screenshot_file_id:
            return payment, False
        payment.screenshot_file_id = screenshot_file_id[:256]
        await session.commit()
        return payment, True

    async def _load_payment(self, session: AsyncSession, payment_id: int) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id)
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        return await session.scalar(stmt)

    async def _load_user(self, session: AsyncSession, user_id: int) -> User:
        stmt = select(User).where(User.id == user_id)
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        user = await session.scalar(stmt)
        if user is None:
            raise AppError(404, "Foydalanuvchi topilmadi.")
        return user

    async def approve_payment(self, session: AsyncSession, payment_id: int, admin_telegram_id: int, now=None) -> dict:
        now = now or utcnow()
        async with resource_lock("payment", payment_id):
            payment = await self._load_payment(session, payment_id)
            if payment is None:
                raise AppError(404, "To‘lov topilmadi.")
            if payment.status == PAYMENT_APPROVED:
                user = await session.get(User, payment.user_id)
                return {
                    "result": "already_approved",
                    "payment_id": payment.id,
                    "user_telegram_id": user.telegram_id if user else 0,
                    "type": payment.type,
                    "amount_uzs": payment.amount_uzs,
                    "balance_uzs": user.balance_uzs if user else 0,
                }
            if payment.status != PAYMENT_PENDING:
                raise AppError(409, "Bu to‘lovni tasdiqlab bo‘lmaydi.")
            user = await self._load_user(session, payment.user_id)
            if payment.type == PAYMENT_PREMIUM:
                apply_premium(user, now)
            elif payment.type == PAYMENT_WALLET:
                before = user.balance_uzs
                user.balance_uzs = before + payment.amount_uzs
                session.add(
                    WalletTransaction(
                        user_id=user.id,
                        type=WALLET_TOPUP,
                        amount_uzs=payment.amount_uzs,
                        balance_before=before,
                        balance_after=user.balance_uzs,
                        description="Balans to‘ldirish",
                        payment_id=payment.id,
                        created_at=now,
                    )
                )
            else:
                raise AppError(422, "To‘lov turi noto‘g‘ri.")
            payment.status = PAYMENT_APPROVED
            payment.reviewed_at = now
            payment.reviewed_by = admin_telegram_id
            user.updated_at = now
            await session.commit()
            return {
                "result": "approved",
                "payment_id": payment.id,
                "user_telegram_id": user.telegram_id,
                "type": payment.type,
                "amount_uzs": payment.amount_uzs,
                "balance_uzs": user.balance_uzs,
                "balance_text": format_uzs(user.balance_uzs),
                "expires_at": user.subscription_expires_at.isoformat(),
            }

    async def reject_payment(self, session: AsyncSession, payment_id: int, admin_telegram_id: int, now=None) -> dict:
        now = now or utcnow()
        async with resource_lock("payment", payment_id):
            payment = await self._load_payment(session, payment_id)
            if payment is None:
                raise AppError(404, "To‘lov topilmadi.")
            if payment.status == PAYMENT_REJECTED:
                user = await session.get(User, payment.user_id)
                return {
                    "result": "already_rejected",
                    "payment_id": payment.id,
                    "user_telegram_id": user.telegram_id if user else 0,
                    "type": payment.type,
                    "amount_uzs": payment.amount_uzs,
                }
            if payment.status != PAYMENT_PENDING:
                raise AppError(409, "Bu to‘lovni rad etib bo‘lmaydi.")
            user = await session.get(User, payment.user_id)
            payment.status = PAYMENT_REJECTED
            payment.reviewed_at = now
            payment.reviewed_by = admin_telegram_id
            await session.commit()
            return {
                "result": "rejected",
                "payment_id": payment.id,
                "user_telegram_id": user.telegram_id if user else 0,
                "type": payment.type,
                "amount_uzs": payment.amount_uzs,
                "balance_uzs": user.balance_uzs if user else 0,
            }

    async def get_pending_payments(self, session: AsyncSession, limit: int = 50) -> list[Payment]:
        rows = await session.scalars(
            select(Payment).where(Payment.status == PAYMENT_PENDING).order_by(Payment.created_at.asc()).limit(limit)
        )
        return list(rows)

    async def list_user_payments(self, session: AsyncSession, user_id: int, limit: int = 20) -> list[Payment]:
        rows = await session.scalars(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc()).limit(limit)
        )
        return list(rows)


manual_payments = ManualPaymentService()
