"""Trial, premium, and expiration status."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import (
    PREMIUM_DAYS,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_EXPIRED,
    SUBSCRIPTION_TRIAL,
    TRIAL_DAYS,
)
from backend.database.models import User
from backend.utils.formatting import as_utc, utcnow


def sync_subscription_status(user: User, now: datetime | None = None) -> bool:
    now = now or utcnow()
    expires = as_utc(user.subscription_expires_at)
    user.subscription_expires_at = expires
    if user.subscription_started_at is not None:
        user.subscription_started_at = as_utc(user.subscription_started_at)
    if expires <= now and user.subscription_status != SUBSCRIPTION_EXPIRED:
        user.subscription_status = SUBSCRIPTION_EXPIRED
        user.updated_at = now
        return True
    return False


def apply_trial(user: User, now: datetime) -> None:
    user.subscription_status = SUBSCRIPTION_TRIAL
    user.subscription_started_at = now
    user.subscription_expires_at = now + timedelta(days=TRIAL_DAYS)
    user.updated_at = now


def add_referral_day(user: User, now: datetime) -> None:
    """Add one day to the current expiration. Never replace that date with now."""
    user.subscription_expires_at = as_utc(user.subscription_expires_at) + timedelta(days=1)
    user.updated_at = now
    if user.subscription_expires_at <= now:
        user.subscription_status = SUBSCRIPTION_EXPIRED
    elif user.subscription_status != SUBSCRIPTION_ACTIVE:
        user.subscription_status = SUBSCRIPTION_TRIAL


def apply_premium(user: User, now: datetime) -> None:
    expires = as_utc(user.subscription_expires_at)
    if expires > now:
        user.subscription_expires_at = expires + timedelta(days=PREMIUM_DAYS)
    else:
        user.subscription_expires_at = now + timedelta(days=PREMIUM_DAYS)
    user.subscription_status = SUBSCRIPTION_ACTIVE
    user.updated_at = now


def subscription_is_valid(user: User, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return as_utc(user.subscription_expires_at) > now and user.subscription_status != SUBSCRIPTION_EXPIRED


async def expire_due_users(session: AsyncSession, now: datetime | None = None) -> int:
    now = now or utcnow()
    users = (
        await session.scalars(
            select(User).where(
                User.subscription_expires_at <= now,
                User.subscription_status != SUBSCRIPTION_EXPIRED,
            )
        )
    ).all()
    for user in users:
        user.subscription_status = SUBSCRIPTION_EXPIRED
        user.updated_at = now
    if users:
        await session.commit()
    return len(users)
