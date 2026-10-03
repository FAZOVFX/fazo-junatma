"""Read-only admin aggregates."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import (
    PAYMENT_APPROVED,
    PAYMENT_PENDING,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_EXPIRED,
    SUBSCRIPTION_TRIAL,
)
from backend.database.models import File, Payment, Referral, User, WalletTransaction
from backend.services.storage_service import StorageService


async def statistics(session: AsyncSession, storage: StorageService) -> dict:
    users_total = int(await session.scalar(select(func.count(User.id))) or 0)

    async def users_with(status: str) -> int:
        return int(await session.scalar(select(func.count(User.id)).where(User.subscription_status == status)) or 0)

    files_total = int(await session.scalar(select(func.count(File.id))) or 0)
    pending = int(
        await session.scalar(select(func.count(Payment.id)).where(Payment.status == PAYMENT_PENDING)) or 0
    )
    approved = int(
        await session.scalar(select(func.count(Payment.id)).where(Payment.status == PAYMENT_APPROVED)) or 0
    )
    approved_amount = int(
        await session.scalar(
            select(func.coalesce(func.sum(Payment.amount_uzs), 0)).where(Payment.status == PAYMENT_APPROVED)
        )
        or 0
    )
    referrals = int(await session.scalar(select(func.count(Referral.id))) or 0)
    report = await storage.build_report(session)
    return {
        "users_total": users_total,
        "users_trial": await users_with(SUBSCRIPTION_TRIAL),
        "users_active": await users_with(SUBSCRIPTION_ACTIVE),
        "users_expired": await users_with(SUBSCRIPTION_EXPIRED),
        "files_total": files_total,
        "files_active": report["active_files"],
        "files_expired": report["expired_files"],
        "files_deleted": report["deleted_files"],
        "payments_pending": pending,
        "payments_approved": approved,
        "approved_amount_uzs": approved_amount,
        "referrals_total": referrals,
        "active_storage_bytes": report["active_bytes"],
        "storage": report,
    }


async def list_users(session: AsyncSession, limit: int = 30) -> list[User]:
    rows = await session.scalars(select(User).order_by(User.created_at.desc()).limit(limit))
    return list(rows)


async def list_wallet_operations(session: AsyncSession, limit: int = 30) -> list[WalletTransaction]:
    rows = await session.scalars(
        select(WalletTransaction).order_by(WalletTransaction.created_at.desc()).limit(limit)
    )
    return list(rows)
